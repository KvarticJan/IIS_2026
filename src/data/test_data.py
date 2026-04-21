import shutil
import sys
import os
from pathlib import Path

import pandas as pd
from evidently import Report

try:
    from evidently.presets import DataDriftPreset, DataSummaryPreset
except ImportError:
    from evidently.presets.dataset_stats import DataSummaryPreset
    from evidently.presets.drift import DataDriftPreset


PREPROCESSED_DIR = Path("data/preprocessed/air")
REFERENCE_DIR = Path("data/reference/air")
REPORTS_DIR = Path("reports/data_testing")
REFRESH_ON_FAILURE = os.getenv("EVIDENTLY_REFRESH_REFERENCE_ON_FAILURE", "").strip().lower() in {"1", "true", "yes"}


def _collect_test_statuses(payload: object) -> list[str]:
    statuses: list[str] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("status"), str):
            statuses.append(payload["status"])
        for value in payload.values():
            statuses.extend(_collect_test_statuses(value))
    elif isinstance(payload, list):
        for item in payload:
            statuses.extend(_collect_test_statuses(item))
    return statuses


def test_data() -> int:
    PREPROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []

    if REFRESH_ON_FAILURE:
        print("Reference refresh mode is enabled for failed Evidently checks.")

    for current_path in sorted(PREPROCESSED_DIR.glob("*.csv")):
        station = current_path.stem
        reference_path = REFERENCE_DIR / current_path.name
        report_path = REPORTS_DIR / f"{station}.html"

        current = pd.read_csv(current_path)
        if not reference_path.exists():
            print(f"Reference file not found for {station}. Bootstrapping from current data.")
            shutil.copy2(current_path, reference_path)

        reference = pd.read_csv(reference_path)

        comparable_reference = reference.drop(columns=["date_to"], errors="ignore")
        comparable_current = current.drop(columns=["date_to"], errors="ignore")

        if list(comparable_reference.columns) != list(comparable_current.columns):
            failures.append(f"{station}: column mismatch")
            continue

        usable_columns = [
            column
            for column in comparable_current.columns
            if comparable_reference[column].notna().sum() >= 2 and comparable_current[column].notna().sum() >= 2
        ]
        if not usable_columns:
            print(f"No comparable numeric data for {station}; refreshing reference without drift calculation.")
            shutil.copy2(current_path, reference_path)
            report_path.write_text(
                "<html><body><h1>Evidently skipped</h1><p>No comparable numeric data was available.</p></body></html>",
                encoding="utf-8",
            )
            continue

        comparable_reference = comparable_reference[usable_columns]
        comparable_current = comparable_current[usable_columns]

        report = Report(
            metrics=[
                DataSummaryPreset(),
                DataDriftPreset(),
            ],
            include_tests=True,
        )
        result = report.run(reference_data=comparable_reference, current_data=comparable_current)
        result.save_html(str(report_path))

        statuses = _collect_test_statuses(result.dict())
        station_success = bool(statuses) and all(status in {"SUCCESS", "PASSED"} for status in statuses)

        if not station_success:
            if REFRESH_ON_FAILURE:
                shutil.copy2(current_path, reference_path)
                print(f"Data tests failed for {station}, but reference was refreshed because refresh mode is enabled.")
                continue
            failures.append(station)
            print(f"Data tests failed for {station}.")
            continue

        shutil.copy2(current_path, reference_path)
        print(f"Data tests passed for {station}.")

    if failures:
        print(f"Data drift or schema checks failed for: {', '.join(failures)}")
        return 1

    print("Data tests passed for all stations.")
    return 0


if __name__ == "__main__":
    sys.exit(test_data())
