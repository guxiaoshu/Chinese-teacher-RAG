#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _extract_juan_start_years(segment_index_payload: Dict[str, Any]) -> Dict[str, Optional[int]]:
    by_juan: Dict[int, list[tuple[int, Optional[int]]]] = {}
    for seg in segment_index_payload.get("segments", {}).values():
        juan = int(seg["juan_index"])
        segment = int(seg["segment_index"])
        year = seg.get("year")
        by_juan.setdefault(juan, []).append((segment, year))

    juan_start_year: Dict[str, Optional[int]] = {}
    for juan, segs in by_juan.items():
        segs_sorted = sorted(segs, key=lambda t: t[0])
        first_year = segs_sorted[0][1] if segs_sorted else None
        if first_year is not None:
            juan_start_year[str(juan)] = int(first_year)
            continue

        non_null = [y for _, y in segs_sorted if y is not None]
        juan_start_year[str(juan)] = int(min(non_null)) if non_null else None

    # stable order by numeric juan index
    return dict(sorted(juan_start_year.items(), key=lambda kv: int(kv[0])))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build data/juan_year_index.json from data/segment_year_index.json")
    parser.add_argument("--input", default="data/segment_year_index.json", help="Path to segment_year_index.json")
    parser.add_argument("--output", default="data/juan_year_index.json", help="Output JSON path")
    parser.add_argument("--version", default="v1", help="Artifact version string")

    args = parser.parse_args()

    with Path(args.input).open("r", encoding="utf-8") as f:
        seg_payload = json.load(f)

    juan_start_year = _extract_juan_start_years(seg_payload)

    payload = {
        "version": args.version,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "juan_start_year": juan_start_year,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    missing = sum(1 for y in juan_start_year.values() if y is None)
    print(f"Wrote {args.output} (juans={len(juan_start_year)}, missing={missing})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
