"""Download the RFCs in data/rfc_list.yaml into data/raw/. Run: make fetch"""

import sys
from pathlib import Path

from app.ingest.fetch import fetch_rfcs
from app.ingest.rfc_list import load_rfc_list

RAW_DIR = Path("data/raw")


def main() -> int:
    result = fetch_rfcs(load_rfc_list(), RAW_DIR)
    print(
        f"downloaded {len(result.downloaded)}, skipped {len(result.skipped)}, "
        f"failed {len(result.failed)}"
    )
    for number, message in result.failed.items():
        print(f"rfc{number}: {message}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
