#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from zztj_pipeline.segment_year_index import build_segment_year_index, load_book, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Build data/segment_year_index.json from adapted_book.json")
    parser.add_argument("--input", default="adapted_book.json", help="Path to adapted_book.json")
    parser.add_argument("--output", default="data/segment_year_index.json", help="Output JSON path")
    parser.add_argument(
        "--cutoff-year",
        type=int,
        default=-1,
        help=(
            "Ambiguous-year policy knob for parenthesized numeric years: "
            "if parsed year N <= cutoff_year, treat as BCE (-N). (default: -1, i.e. keep as CE)"
        ),
    )
    parser.add_argument("--version", default="v1", help="Artifact version string")
    parser.add_argument(
        "--overrides",
        default=None,
        help="Optional path to segment year overrides JSON (e.g. data/segment_year_overrides.json)",
    )

    args = parser.parse_args()

    book = load_book(Path(args.input))
    overrides = None
    if args.overrides:
        with Path(args.overrides).open("r", encoding="utf-8") as f:
            overrides = json.load(f)

    payload = build_segment_year_index(
        book=book,
        cutoff_year=args.cutoff_year,
        overrides=overrides,
        version=args.version,
    )
    write_json(Path(args.output), payload)
    print(f"Wrote {args.output} (segments={len(payload['segments'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
