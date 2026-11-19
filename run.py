"""Run the whole pipeline: download, check and load, build the dashboard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import dashboard
import fetch
import load

if __name__ == "__main__":
    fetch.fetch()
    print("Downloaded 4 files")
    print(load.load().to_string(index=False))
    dashboard.main()
