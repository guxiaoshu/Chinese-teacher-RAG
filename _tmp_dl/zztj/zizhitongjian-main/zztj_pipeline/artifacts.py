from __future__ import annotations

from typing import Dict, Optional, TypedDict


class SegmentYearIndexEntry(TypedDict):
    juan_index: int
    segment_index: int
    segment_start_time_raw: Optional[str]
    year: Optional[int]
    parse_method: Optional[str]
    confidence: float


class SegmentYearIndexPayload(TypedDict):
    version: str
    cutoff_year: int
    generated_at: str
    segments: Dict[str, SegmentYearIndexEntry]  # key: "{juan_index}-{segment_index}"


class SegmentYearOverrideEntry(TypedDict, total=False):
    year: Optional[int]
    reason: str


class SegmentYearOverridesPayload(TypedDict, total=False):
    version: str
    notes: str
    overrides: Dict[str, SegmentYearOverrideEntry]


class JuanYearIndexPayload(TypedDict):
    version: str
    generated_at: str
    juan_start_year: Dict[str, Optional[int]]  # key is juan_index serialized as string


class LocationGeocodingOverrideEntry(TypedDict, total=False):
    coordinates: list[float]  # [lng, lat]
    notes: str


class LocationGeocodingEntry(TypedDict, total=False):
    location_id: str
    canonical_name: str
    modern_name: str
    query: str
    coordinates: Optional[list[float]]
    candidate_coordinates: Optional[list[float]]
    candidate_count: Optional[int]
    confidence: float
    source: str
    evidence: str
    info: Optional[str]
    infocode: Optional[str]
    needs_review: bool
    attempts: int
    updated_at: str


class LocationGeocodingPayload(TypedDict):
    version: str
    provider: str
    generated_at: str
    locations: Dict[str, LocationGeocodingEntry]
    overrides: Dict[str, LocationGeocodingOverrideEntry]
