#!/usr/bin/env python3
"""Merge geocoding cache into unified knowledge base.

- Input: `data/unified_knowledge.json`
- Input: `data/location_geocoding.json`
- Output: updates unified KB in-place (or to `--out`).

This fills `locations[*].coordinates` with WGS84 `[lng, lat]`.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _now_iso() -> str:
    return datetime.now().isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _normalize_coords(coords: Any) -> Optional[Tuple[float, float]]:
    if coords is None:
        return None
    if not isinstance(coords, (list, tuple)) or len(coords) != 2:
        return None
    try:
        lng = float(coords[0])
        lat = float(coords[1])
    except Exception:
        return None
    return (lng, lat)


def _set_geocoding_note(kb_loc: Dict[str, Any], entry: Dict[str, Any], status: str) -> None:
    """Attach a human-reviewable geocoding note onto a location.

    We intentionally keep this as plain JSON (extra fields) so it won't break
    existing consumers of `data/unified_knowledge.json`.
    """

    kb_loc["geocoding"] = {
        "status": status,
        "source": entry.get("source"),
        "query": entry.get("query"),
        "needs_review": entry.get("needs_review"),
        "evidence": entry.get("evidence"),
        "info": entry.get("info"),
        "infocode": entry.get("infocode"),
        "candidate_count": entry.get("candidate_count"),
        "candidate_coordinates": entry.get("candidate_coordinates"),
        "updated_at": entry.get("updated_at"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge location geocoding cache into unified KB")
    parser.add_argument("--kb", default="data/unified_knowledge.json", help="Path to unified KB JSON")
    parser.add_argument("--geocoding", default="data/location_geocoding.json", help="Path to geocoding cache JSON")
    parser.add_argument("--out", default="", help="Write output to this path instead of updating KB in-place")
    parser.add_argument("--require-review-ok", action="store_true", help="Skip entries marked needs_review=true")
    args = parser.parse_args()

    kb_path = Path(args.kb)
    geo_path = Path(args.geocoding)

    kb = _load_json(kb_path)
    geo = _load_json(geo_path)

    kb_locations = kb.get("locations") or {}
    geo_locations = (geo.get("locations") or {})

    updated = 0
    noted = 0
    skipped_review = 0
    missing_in_kb = 0

    for loc_id, entry in geo_locations.items():
        if loc_id not in kb_locations:
            missing_in_kb += 1
            continue

        kb_loc = kb_locations[loc_id]

        needs_review = entry.get("needs_review") is True
        coords = _normalize_coords(entry.get("coordinates"))

        if needs_review or coords is None:
            if args.require_review_ok and needs_review:
                skipped_review += 1
                continue
            # Don't fill coordinates; instead attach a message for humans.
            _set_geocoding_note(
                kb_loc,
                entry=entry,
                status=("needs_review" if needs_review else "failed"),
            )
            kb_loc["updated_at"] = _now_iso()
            noted += 1
            continue

        # Confident coordinate: merge into KB.
        before = kb_loc.get("coordinates")
        before_norm = _normalize_coords(before)
        if before_norm != coords:
            kb_loc["coordinates"] = [coords[0], coords[1]]
            updated += 1

        _set_geocoding_note(kb_loc, entry=entry, status="ok")
        kb_loc["updated_at"] = _now_iso()

    out_path = Path(args.out) if args.out else kb_path
    _save_json(out_path, kb)

    print(
        f"Wrote {out_path} (updated={updated}, noted={noted}, skipped_review={skipped_review}, missing_in_kb={missing_in_kb})"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
