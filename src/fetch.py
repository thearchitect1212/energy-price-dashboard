"""Download daily energy prices and monthly US consumer prices (CPI).

The files come from the open "datasets" project on GitHub, which republishes
US Energy Information Administration (EIA) prices and Bureau of Labor
Statistics (BLS) CPI figures and refreshes them automatically.
"""
from pathlib import Path

import requests

BASE = "https://raw.githubusercontent.com/datasets"
SOURCES = {
    "wti": f"{BASE}/oil-prices/main/data/wti-daily.csv",        # US crude oil, $ per barrel
    "brent": f"{BASE}/oil-prices/main/data/brent-daily.csv",    # global crude oil, $ per barrel
    "natural_gas": f"{BASE}/natural-gas/main/data/daily.csv",   # Henry Hub, $ per million BTU
    "cpi": f"{BASE}/cpi-us/main/data/cpiai.csv",                # US consumer price index, monthly
}
RAW_DIR = Path("data/raw")


def fetch(raw_dir: Path = RAW_DIR) -> dict[str, Path]:
    """Save each source file to disk and return {name: path}."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, url in SOURCES.items():
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        paths[name] = raw_dir / f"{name}.csv"
        paths[name].write_bytes(response.content)
    return paths


if __name__ == "__main__":
    for name, path in fetch().items():
        print(f"Saved {name} to {path}")
