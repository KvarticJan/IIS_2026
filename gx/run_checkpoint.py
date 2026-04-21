import sys
from pathlib import Path

import great_expectations as gx


CONTEXT_ROOT = Path(__file__).resolve().parent
PREPROCESSED_DIR = CONTEXT_ROOT.parent / "data" / "preprocessed" / "air"
DATASOURCE_NAME = "air_quality"
ASSET_NAME = "air_quality_data"
SUITE_NAME = "air_quality_suite"
CHECKPOINT_NAME = "air_quality_checkpoint"


def _get_context():
    return gx.get_context(context_root_dir=str(CONTEXT_ROOT))


def _get_or_create_datasource(context):
    try:
        datasource = context.get_datasource(DATASOURCE_NAME)
    except Exception:
        datasource = context.sources.add_pandas_filesystem(
            name=DATASOURCE_NAME,
            base_directory=str(PREPROCESSED_DIR.resolve()),
        )
    return datasource


def _get_or_create_asset(datasource):
    try:
        return datasource.get_asset(ASSET_NAME)
    except Exception:
        return datasource.add_csv_asset(
            name=ASSET_NAME,
            batching_regex=r"(?P<station>[A-Z0-9]+)\.csv",
        )


def _configure_expectation_suite(context, asset, station: str) -> None:
    expectation_suite = context.add_or_update_expectation_suite(expectation_suite_name=SUITE_NAME)
    expectation_suite.expectations = []
    context.save_expectation_suite(expectation_suite=expectation_suite, expectation_suite_name=SUITE_NAME)

    validator = context.get_validator(
        batch_request=asset.build_batch_request(options={"station": station}),
        expectation_suite_name=SUITE_NAME,
    )
    validator.expect_table_row_count_to_be_between(min_value=150)
    validator.expect_table_columns_to_match_set(
        column_set=["date_to", "PM10", "PM2.5"],
        exact_match=True,
    )
    validator.expect_column_values_to_not_be_null(column="date_to")
    validator.expect_column_values_to_be_unique(column="date_to")
    validator.expect_column_values_to_match_regex(
        column="date_to",
        regex=r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$",
    )
    validator.expect_column_values_to_be_between(column="PM10", min_value=0, max_value=300, mostly=0.95)
    validator.expect_column_values_to_be_between(column="PM2.5", min_value=0, max_value=300, mostly=0.95)
    validator.save_expectation_suite(discard_failed_expectations=False)


def run_checkpoint() -> int:
    station_codes = sorted(path.stem for path in PREPROCESSED_DIR.glob("*.csv"))
    if not station_codes:
        print("No preprocessed station files found for validation.")
        return 1

    context = _get_context()
    datasource = _get_or_create_datasource(context)
    asset = _get_or_create_asset(datasource)

    _configure_expectation_suite(context, asset, station_codes[0])

    validations = [
        {
            "batch_request": asset.build_batch_request(options={"station": station}),
            "expectation_suite_name": SUITE_NAME,
        }
        for station in station_codes
    ]

    checkpoint = context.add_or_update_checkpoint(
        name=CHECKPOINT_NAME,
        validations=validations,
    )
    checkpoint_result = checkpoint.run()
    context.build_data_docs()

    success = checkpoint_result["success"]
    if success:
        print("Validation passed for all stations.")
        return 0

    print("Validation failed.")
    return 1


if __name__ == "__main__":
    sys.exit(run_checkpoint())
