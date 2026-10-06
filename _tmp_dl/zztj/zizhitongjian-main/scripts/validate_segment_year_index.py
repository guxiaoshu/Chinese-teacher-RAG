#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from zztj_pipeline.segment_year_index import validate_segment_year_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate data/segment_year_index.json")
    parser.add_argument("--input", default="data/segment_year_index.json", help="Path to segment_year_index.json")
    parser.add_argument("--fail", action="store_true", help="Exit non-zero if any errors")

    args = parser.parse_args()

    with Path(args.input).open("r", encoding="utf-8") as f:
        payload = json.load(f)

    errors = validate_segment_year_index(payload)
    if not errors:
        print("OK: no validation errors")
        return 0

    print(f"Found {len(errors)} validation error(s):")
    for e in errors[:200]:
        print(f"- {e}")

    if len(errors) > 200:
        print(f"... truncated, total={len(errors)}")

    return 1 if args.fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
