"""Write a valid sample lesson package zip to /tmp for manual testing.

Run from backend/ with the venv active:

    python scripts/make_sample_package.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.factories.package import build_package  # noqa: E402


def main() -> None:
    out_dir = Path("/tmp/supercpe-sample")
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = build_package(out_dir)
    print(f"Sample package written to {zip_path}")


if __name__ == "__main__":
    main()
