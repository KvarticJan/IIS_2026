import json
import os
import random
import time
from pathlib import Path

import joblib
import mlflow
import numpy as np
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler

os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

import tensorflow as tf
import tf2onnx
from tensorflow.keras.callbacks import EarlyStopping, LambdaCallback
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from tensorflow.keras.models import Sequential

from preprocess import DatePreprocessor, SlidingWindowTransformer


PARAMS_PATH = Path("params.yaml")
PREPROCESSED_DIR = Path("data/preprocessed/air")
MODELS_DIR = Path("models")
REPORTS_DIR = Path("reports/model_training")
MLRUNS_DIR = Path("mlruns")


def debug(message: str) -> None:
    elapsed = time.strftime("%H:%M:%S")
    print(f"[{elapsed}] {message}", flush=True)


def build_model(input_shape: tuple[int, int]) -> Sequential:
    debug(f"Building model for input shape {input_shape}")
    model = Sequential()
    model.add(Input(shape=input_shape))
    model.add(LSTM(16, return_sequences=False))
    model.add(Dropout(0.2))
    model.add(Dense(1))
    model.compile(optimizer="adam", loss="mean_squared_error")
    return model


def _load_params() -> dict:
    return yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))


def _configure_mlflow(config: dict) -> bool:
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    username = os.getenv("MLFLOW_TRACKING_USERNAME", "").strip()
    password = os.getenv("MLFLOW_TRACKING_PASSWORD", "").strip()
    experiment_config = config.get("experiment_tracking", {})

    if not tracking_uri:
        remote_uri = str(experiment_config.get("tracking_uri", "")).strip()
        if remote_uri and username and password:
            tracking_uri = remote_uri
        else:
            tracking_uri = MLRUNS_DIR.resolve().as_uri()

    experiment_name = str(experiment_config.get("experiment_name", "IIS_2026_train"))
    debug(f"Configuring MLflow tracking URI: {tracking_uri}")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    return tracking_uri.startswith("http://") or tracking_uri.startswith("https://")


def _build_pipeline(target_col: str, window_size: int) -> Pipeline:
    numeric_transformer = Pipeline(
        [
            ("fillna", SimpleImputer(strategy="mean")),
            ("normalize", MinMaxScaler()),
        ]
    )

    preprocess = ColumnTransformer(
        [
            ("numeric_transformer", numeric_transformer, [target_col]),
        ]
    )

    return Pipeline(
        [
            ("preprocess", preprocess),
            ("sliding_window_transformer", SlidingWindowTransformer(window_size)),
        ]
    )


def _inverse_transform_targets(pipeline: Pipeline, values: np.ndarray) -> np.ndarray:
    scaler = pipeline.named_steps["preprocess"].named_transformers_["numeric_transformer"].named_steps["normalize"]
    return scaler.inverse_transform(values.reshape(-1, 1)).reshape(-1)


def _save_metrics(metrics_path: Path, metrics: dict) -> None:
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def _resolve_stations(station_config: str | list[str]) -> list[str]:
    if isinstance(station_config, list):
        requested = [str(station).strip() for station in station_config]
    else:
        station_value = str(station_config).strip()
        if station_value.lower() == "all":
            return sorted(path.stem for path in PREPROCESSED_DIR.glob("*.csv"))
        requested = [station.strip() for station in station_value.split(",")]

    return [station for station in requested if station]


def _export_onnx_model(model: Sequential, input_shape: tuple[int, int], onnx_path: Path) -> None:
    debug(f"Saving ONNX model to {onnx_path}")
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    input_signature = (tf.TensorSpec((None, input_shape[0], input_shape[1]), tf.float32, name="input"),)

    if not hasattr(model, "output_names"):
        model.output_names = ["output"]

    tf2onnx.convert.from_keras(
        model,
        input_signature=input_signature,
        opset=13,
        output_path=str(onnx_path),
    )


def _train_station(config: dict, station: str, uses_remote_mlflow: bool) -> dict:
    station_start = time.perf_counter()
    params = config["train"]
    test_size = int(params["test_size"])
    random_state = int(params["random_state"])
    window_size = int(params["window_size"])
    target_col = params["target_col"]
    epochs = int(params["epochs"])
    batch_size = int(params["batch_size"])
    validation_split = float(params["validation_split"])
    patience = int(params["patience"])

    with mlflow.start_run(run_name=f"train_{station}"):
        mlflow.log_params(
            {
                "station": station,
                "test_size": test_size,
                "random_state": random_state,
                "window_size": window_size,
                "target_col": target_col,
                "epochs": epochs,
                "batch_size": batch_size,
                "validation_split": validation_split,
                "patience": patience,
                "tracking_mode": "remote" if uses_remote_mlflow else "local",
            }
        )

        dataset_path = PREPROCESSED_DIR / f"{station}.csv"
        debug(f"Loading dataset from {dataset_path}")
        if not dataset_path.exists():
            raise ValueError(f"Dataset for {station} does not exist: {dataset_path}")

        df = pd.read_csv(dataset_path)
        if target_col not in df.columns:
            raise ValueError(f"Dataset for {station} does not contain target column {target_col}.")

        df[target_col] = pd.to_numeric(df[target_col], errors="coerce")
        minimum_rows = window_size + test_size + 1
        valid_target_rows = int(df[target_col].notna().sum())
        if valid_target_rows < minimum_rows:
            raise ValueError(
                f"Dataset for {station} has too few valid {target_col} values. "
                f"Need at least {minimum_rows}, got {valid_target_rows}."
            )

        debug("Applying date preprocessing and hourly alignment")
        date_preprocessor = DatePreprocessor("date_to")
        df = date_preprocessor.fit_transform(df)
        debug(f"Dataset shape after date preprocessing: {df.shape}")
        mlflow.log_metric("dataset_rows", float(len(df)))

        if len(df) < minimum_rows:
            raise ValueError(
                f"Dataset for {station} is too small for training. Need at least {minimum_rows} rows, got {len(df)}."
            )

        df_train = df.iloc[:-test_size].copy()
        df_test = df.iloc[-(test_size + window_size) :].copy()

        debug("Building preprocessing pipeline")
        pipeline = _build_pipeline(target_col=target_col, window_size=window_size)
        debug("Transforming train/test splits into sliding windows")
        X_train, y_train = pipeline.fit_transform(df_train)
        X_test, y_test = pipeline.transform(df_test)

        debug(f"X_train shape: {X_train.shape}, y_train shape: {y_train.shape}")
        debug(f"X_test shape: {X_test.shape}, y_test shape: {y_test.shape}")
        mlflow.log_params(
            {
                "train_samples": int(X_train.shape[0]),
                "test_samples": int(X_test.shape[0]),
                "input_timesteps": int(X_train.shape[1]),
                "input_features": int(X_train.shape[2]),
            }
        )

        input_shape = (X_train.shape[1], X_train.shape[2])
        model = build_model(input_shape)
        early_stopping = EarlyStopping(monitor="val_loss", patience=patience, restore_best_weights=True)
        epoch_debug = LambdaCallback(
            on_epoch_begin=lambda epoch, logs: debug(f"Starting train epoch {epoch + 1}/{epochs}"),
            on_epoch_end=lambda epoch, logs: debug(f"Finished train epoch {epoch + 1}/{epochs} with logs={logs}"),
        )
        debug("Starting first model.fit on training split")
        model.fit(
            X_train,
            y_train,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
            callbacks=[early_stopping, epoch_debug],
            shuffle=False,
            verbose=2,
        )
        debug("First model.fit completed")

        debug("Running test-set prediction")
        y_pred = model.predict(X_test, verbose=0).reshape(-1)
        y_test_inverse = _inverse_transform_targets(pipeline, y_test.reshape(-1))
        y_pred_inverse = _inverse_transform_targets(pipeline, y_pred)

        mse = mean_squared_error(y_test_inverse, y_pred_inverse)
        mae = mean_absolute_error(y_test_inverse, y_pred_inverse)
        rmse = float(np.sqrt(mse))
        debug(f"Test MAE: {mae}")
        debug(f"Test MSE: {mse}")
        debug(f"Test RMSE: {rmse}")
        mlflow.log_metric("test_mae", mae)
        mlflow.log_metric("test_mse", mse)
        mlflow.log_metric("test_rmse", rmse)

        debug("Preparing full-dataset training data")
        X_full, y_full = pipeline.fit_transform(df)
        tf.keras.backend.clear_session()
        model_full = build_model((X_full.shape[1], X_full.shape[2]))
        full_early_stopping = EarlyStopping(monitor="val_loss", patience=patience, restore_best_weights=True)
        full_epoch_debug = LambdaCallback(
            on_epoch_begin=lambda epoch, logs: debug(f"Starting full epoch {epoch + 1}/{epochs}"),
            on_epoch_end=lambda epoch, logs: debug(f"Finished full epoch {epoch + 1}/{epochs} with logs={logs}"),
        )
        debug("Starting second model.fit on full dataset")
        model_full.fit(
            X_full,
            y_full,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
            callbacks=[full_early_stopping, full_epoch_debug],
            shuffle=False,
            verbose=2,
        )
        debug("Second model.fit completed")

        debug("Running full-dataset prediction")
        y_pred_full = model_full.predict(X_full, verbose=0).reshape(-1)
        y_full_inverse = _inverse_transform_targets(pipeline, y_full.reshape(-1))
        y_pred_full_inverse = _inverse_transform_targets(pipeline, y_pred_full)

        mse_full = mean_squared_error(y_full_inverse, y_pred_full_inverse)
        mae_full = mean_absolute_error(y_full_inverse, y_pred_full_inverse)
        rmse_full = float(np.sqrt(mse_full))
        debug(f"Full dataset MAE: {mae_full}")
        debug(f"Full dataset MSE: {mse_full}")
        debug(f"Full dataset RMSE: {rmse_full}")
        mlflow.log_metric("full_mae", mae_full)
        mlflow.log_metric("full_mse", mse_full)
        mlflow.log_metric("full_rmse", rmse_full)

        model_path = MODELS_DIR / f"model_{station}.keras"
        onnx_path = MODELS_DIR / f"model_{station}.onnx"
        pipeline_path = MODELS_DIR / f"pipeline_{station}.pkl"
        metrics_path = REPORTS_DIR / f"{station}.json"

        debug(f"Saving model to {model_path}")
        model_full.save(model_path)
        mlflow.log_artifact(str(model_path))
        _export_onnx_model(model_full, (X_full.shape[1], X_full.shape[2]), onnx_path)
        mlflow.log_artifact(str(onnx_path))
        debug(f"Saving preprocessing pipeline to {pipeline_path}")
        joblib.dump(pipeline, pipeline_path)
        mlflow.log_artifact(str(pipeline_path))
        debug(f"Saving metrics to {metrics_path}")
        metrics_payload = {
            "station": station,
            "target_col": target_col,
            "duration_seconds": round(time.perf_counter() - station_start, 2),
            "model_path": str(model_path),
            "onnx_path": str(onnx_path),
            "pipeline_path": str(pipeline_path),
            "test": {"mae": mae, "mse": mse, "rmse": rmse},
            "full": {"mae": mae_full, "mse": mse_full, "rmse": rmse_full},
        }
        _save_metrics(metrics_path, metrics_payload)
        mlflow.log_artifact(str(metrics_path))
        debug(f"Training for {station} completed in {round(time.perf_counter() - station_start, 2)} seconds")
        tf.keras.backend.clear_session()
        return metrics_payload


def train_model() -> None:
    start_time = time.perf_counter()
    debug("Loading training parameters")
    config = _load_params()
    params = config["train"]
    station_config = os.getenv("TRAIN_STATION", params["station"])
    stations = _resolve_stations(station_config)
    if not stations:
        raise ValueError("No stations selected for training.")

    random_state = int(params["random_state"])

    debug("Setting reproducibility configuration")
    os.environ["PYTHONHASHSEED"] = str(random_state)
    random.seed(random_state)
    np.random.seed(random_state)
    tf.keras.utils.set_random_seed(random_state)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.threading.set_intra_op_parallelism_threads(1)

    debug("Ensuring output directories exist")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    MLRUNS_DIR.mkdir(parents=True, exist_ok=True)
    uses_remote_mlflow = _configure_mlflow(config)

    summary = {
        "requested_station": station_config,
        "duration_seconds": None,
        "trained": [],
        "skipped": [],
        "failed": [],
    }

    debug(f"Training selected stations: {', '.join(stations)}")
    for station in stations:
        try:
            summary["trained"].append(_train_station(config, station, uses_remote_mlflow))
        except ValueError as exc:
            debug(f"Skipping {station}: {exc}")
            summary["skipped"].append({"station": station, "reason": str(exc)})
        except Exception as exc:
            debug(f"Training failed for {station}: {exc}")
            summary["failed"].append({"station": station, "reason": str(exc)})

    summary["duration_seconds"] = round(time.perf_counter() - start_time, 2)
    summary_path = REPORTS_DIR / "summary.json"
    debug(f"Saving training summary to {summary_path}")
    _save_metrics(summary_path, summary)

    if not summary["trained"]:
        raise RuntimeError("No station models were trained successfully.")

    if summary["failed"]:
        failed_stations = ", ".join(item["station"] for item in summary["failed"])
        raise RuntimeError(f"Training failed for stations: {failed_stations}")

    debug(f"Training completed in {summary['duration_seconds']} seconds")


if __name__ == "__main__":
    train_model()
