from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


DEFAULT_CUTOFF_YEAR = -1


@dataclass(frozen=True)
class ParsedYear:
    year: int
    parse_method: str
    confidence: float


_RE_GONGYUANQIAN = re.compile(r"公元前\s*(\d+)")
_RE_QIAN = re.compile(r"前\s*(\d+)")
_RE_GONGYUAN = re.compile(r"公元\s*(\d+)")
_RE_PAREN_NUMERIC_YEAR = re.compile(r"[（(][^）)]*?[、，,]\s*(\d{1,4})\s*(?:年)?\s*[）)]")


def parse_year_from_segment_start_time(raw: str, *, cutoff_year: int = DEFAULT_CUTOFF_YEAR) -> Optional[ParsedYear]:
    """Parse a numeric year from a segment_start_time string.

    V1 policy:
    - If explicitly marked as BCE (e.g. 公元前/前), return negative year.
    - If explicitly marked as CE (e.g. 公元), return positive year.
    - Otherwise return None.

    Note: `cutoff_year` is reserved for future mixed BCE/CE policies.
    """
    if not raw:
        return None

    match = _RE_GONGYUANQIAN.search(raw)
    if match:
        n = int(match.group(1))
        return ParsedYear(year=-n, parse_method="regex:公元前(\\d+)", confidence=1.0)

    # Must check 公元前 before 前
    match = _RE_QIAN.search(raw)
    if match:
        n = int(match.group(1))
        return ParsedYear(year=-n, parse_method="regex:前(\\d+)", confidence=1.0)

    match = _RE_GONGYUAN.search(raw)
    if match:
        n = int(match.group(1))
        return ParsedYear(year=n, parse_method="regex:公元(\\d+)", confidence=1.0)

    # Common AD notation in the dataset: "（...、3）", "（...、116）", "（...、958）"
    match = _RE_PAREN_NUMERIC_YEAR.search(raw)
    if match:
        n = int(match.group(1))
        # Policy knob: if callers want to force early ambiguous years to BCE, they can
        # set cutoff_year accordingly; V1 default keeps these as CE.
        if cutoff_year is not None and n <= cutoff_year:
            return ParsedYear(year=-n, parse_method="regex:(paren)year<=cutoff", confidence=0.7)
        return ParsedYear(year=n, parse_method="regex:(paren)(\\d+)", confidence=0.9)

    _ = cutoff_year  # reserved
    return None
