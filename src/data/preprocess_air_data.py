from pathlib import Path

import numpy as np
import pandas as pd
from lxml import etree as ET
import yaml

RAW_DATA_PATH = Path("data/raw/air/air_data.xml")
PREPROCESSED_DIR = Path("data/preprocessed/air")
CSV_COLUMNS = ["date_to", "PM10", "PM2.5"]
PARAMS_PATH = Path("params.yaml")


def _normalize_measurement(value: str | None) -> float | str:
    if value is None or value == "":
        return np.nan
    if value == "<1":
        return 1.0
    if value == "<2":
        return 2.0
    return value


def _load_station_filter() -> str:
    params = yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))
    return str(params.get("preprocess", {}).get("station", "all"))


def preprocess_air_data() -> None:
    PREPROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    with RAW_DATA_PATH.open("rb") as file:
        tree = ET.parse(file)
        root = tree.getroot()

    print(f"Version: {root.attrib['verzija']}")
    print(f"Source: {root.findtext('vir')}")
    print(f"Suggested Capture: {root.findtext('predlagan_zajem')}")
    print(f"Suggested Capture Period: {root.findtext('predlagan_zajem_perioda')}")
    print(f"Preparation Date: {root.findtext('datum_priprave')}")

    station_codes = sorted(set(tree.xpath("//postaja/@sifra")))
    station_filter = _load_station_filter()
    if station_filter.lower() != "all":
        station_codes = [station_code for station_code in station_codes if station_code == station_filter]

    print(f"Processing {len(station_codes)} stations")

    for station_code in station_codes:
        output_path = PREPROCESSED_DIR / f"{station_code}.csv"
        if output_path.exists():
            df = pd.read_csv(output_path)
        else:
            df = pd.DataFrame(columns=CSV_COLUMNS)

        station_elements = tree.xpath(f'//postaja[@sifra="{station_code}"]')
        new_rows = []
        for station in station_elements:
            new_rows.append(
                {
                    "date_to": station.findtext("datum_do"),
                    "PM10": _normalize_measurement(station.findtext("pm10")),
                    "PM2.5": _normalize_measurement(station.findtext("pm2.5")),
                }
            )

        if new_rows:
            df = pd.concat([df, pd.DataFrame(new_rows, columns=CSV_COLUMNS)], ignore_index=True)

        df = df.drop_duplicates(subset=["date_to"])
        df = df.sort_values(by="date_to")
        df["PM10"] = pd.to_numeric(df["PM10"], errors="coerce")
        df["PM2.5"] = pd.to_numeric(df["PM2.5"], errors="coerce")
        df.to_csv(output_path, index=False)

        print(f"Saved {len(df)} rows to {output_path}")


if __name__ == "__main__":
    preprocess_air_data()
