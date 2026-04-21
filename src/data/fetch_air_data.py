from datetime import datetime
from pathlib import Path

import requests
import yaml

RAW_DATA_PATH = Path("data/raw/air/air_data.xml")
PARAMS_PATH = Path("params.yaml")


def _load_air_data_url() -> str:
    params = yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))
    return params["fetch"]["url"]


def fetch_air_data() -> None:
    RAW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    air_data_url = _load_air_data_url()
    session = requests.Session()
    session.trust_env = False
    response = session.get(air_data_url, timeout=60)
    response.raise_for_status()
    RAW_DATA_PATH.write_bytes(response.content)

    print(f"Fetching successful. Data saved to {RAW_DATA_PATH} at {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    fetch_air_data()
