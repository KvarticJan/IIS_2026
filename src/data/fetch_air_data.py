from datetime import datetime
from pathlib import Path

import requests

AIR_DATA_URL = "https://www.arso.gov.si/xml/zrak/ones_zrak_urni_podatki_7dni.xml"
RAW_DATA_PATH = Path("data/raw/air/air_data.xml")


def fetch_air_data() -> None:
    RAW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.trust_env = False
    response = session.get(AIR_DATA_URL, timeout=60)
    response.raise_for_status()
    RAW_DATA_PATH.write_bytes(response.content)

    print(f"Fetching successful. Data saved to {RAW_DATA_PATH} at {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    fetch_air_data()
