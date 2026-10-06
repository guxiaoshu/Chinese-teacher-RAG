from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .artifacts import SegmentYearIndexPayload
from .time_parsing import parse_year_from_segment_start_time


def iter_segments(book: List[Dict[str, Any]]) -> Iterable[Tuple[int, int, Dict[str, Any]]]:
    """Yield (juan_index, segment_index, segment_dict) in stable order."""
    for juan in sorted(book, key=lambda j: j.get("juan_index", 0)):
        juan_index = int(juan["juan_index"])
        for segment in sorted(juan.get("segments", []), key=lambda s: s.get("segment_index", 0)):
            segment_index = int(segment["segment_index"])
            yield juan_index, segment_index, segment


def build_segment_year_index(
    *,
    book: List[Dict[str, Any]],
    cutoff_year: int = -1,
    overrides: Optional[Dict[str, Any]] = None,
    version: str = "v1",
) -> SegmentYearIndexPayload:
    segments: Dict[str, Any] = {}

    overrides_map: Dict[str, Any] = {}
    if overrides:
        overrides_map = overrides.get("overrides", overrides)  # accept either wrapped or raw mapping

    for juan_index, segment_index, segment in iter_segments(book):
        raw = segment.get("segment_start_time")
        parsed = parse_year_from_segment_start_time(raw or "", cutoff_year=cutoff_year)

        key = f"{juan_index}-{segment_index}"

        override = overrides_map.get(key)
        if override is not None:
            override_year = override.get("year") if isinstance(override, dict) else override
            segments[key] = {
                "juan_index": juan_index,
                "segment_index": segment_index,
                "segment_start_time_raw": raw,
                "year": int(override_year) if override_year is not None else None,
                "parse_method": "override",
                "confidence": 1.0,
            }
            continue

        if parsed is None:
            segments[key] = {
                "juan_index": juan_index,
                "segment_index": segment_index,
                "segment_start_time_raw": raw,
                "year": None,
                "parse_method": None,
                "confidence": 0.0,
            }
        else:
            segments[key] = {
                "juan_index": juan_index,
                "segment_index": segment_index,
                "segment_start_time_raw": raw,
                "year": parsed.year,
                "parse_method": parsed.parse_method,
                "confidence": parsed.confidence,
            }

    payload: SegmentYearIndexPayload = {
        "version": version,
        "cutoff_year": cutoff_year,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "segments": segments,
    }

    return payload


def load_book(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("adapted_book.json must be a list of juans")
    return data


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _extract_juan_start_years(segment_index_payload: Dict[str, Any]) -> Dict[int, Optional[int]]:
    by_juan: Dict[int, List[Tuple[int, Optional[int]]]] = {}
    for seg in segment_index_payload.get("segments", {}).values():
        juan = int(seg["juan_index"])
        segment = int(seg["segment_index"])
        year = seg.get("year")
        by_juan.setdefault(juan, []).append((segment, year))

    juan_start_year: Dict[int, Optional[int]] = {}
    for juan, segs in by_juan.items():
        segs_sorted = sorted(segs, key=lambda t: t[0])
        first_year = segs_sorted[0][1] if segs_sorted else None
        if first_year is not None:
            juan_start_year[juan] = int(first_year)
            continue

        # fallback: min non-null year in the juan
        non_null = [y for _, y in segs_sorted if y is not None]
        juan_start_year[juan] = int(min(non_null)) if non_null else None

    return dict(sorted(juan_start_year.items(), key=lambda kv: kv[0]))


def validate_segment_year_index(
    segment_index_payload: Dict[str, Any],
) -> List[str]:
    """Return a list of human-readable validation errors."""
    errors: List[str] = []

    # Within-juan non-decreasing by segment_index (ignoring null years)
    by_juan: Dict[int, List[Tuple[int, Optional[int], str]]] = {}
    for key, seg in segment_index_payload.get("segments", {}).items():
        juan = int(seg["juan_index"])
        segment = int(seg["segment_index"])
        year = seg.get("year")
        by_juan.setdefault(juan, []).append((segment, year, key))

    for juan, items in sorted(by_juan.items(), key=lambda kv: kv[0]):
        items_sorted = sorted(items, key=lambda t: t[0])
        last_year: Optional[int] = None
        last_key: Optional[str] = None
        for _, year, key in items_sorted:
            if year is None:
                continue
            if last_year is not None and year < last_year:
                errors.append(
                    f"within-juan monotonicity violation: juan={juan} {last_key} year={last_year} -> {key} year={year}"
                )
            last_year = int(year)
            last_key = key

    # Across-juan sequential-on-year invariant (start years should be non-decreasing)
    juan_start_year = _extract_juan_start_years(segment_index_payload)
    last_juan: Optional[int] = None
    last_start_year: Optional[int] = None
    for juan, start_year in juan_start_year.items():
        if start_year is None:
            errors.append(f"missing juan_start_year: juan={juan}")
            continue
        if last_start_year is not None and start_year < last_start_year:
            errors.append(
                f"across-juan start-year violation: juan={last_juan} start_year={last_start_year} -> juan={juan} start_year={start_year}"
            )
        last_juan = juan
        last_start_year = int(start_year)

    return errors
