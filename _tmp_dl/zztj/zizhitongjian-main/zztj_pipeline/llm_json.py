"""Utilities for extracting JSON payloads from LLM responses.

LLMs often wrap JSON in markdown code fences or append explanatory text.
This module provides a tolerant extractor with a small set of safe repairs.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict


class LLMJSONParseError(ValueError):
    pass


_CODE_FENCE_RE = re.compile(r"```\s*(?:json)?\s*", re.IGNORECASE)


def extract_json_from_response(content: str) -> Dict[str, Any]:
    """Extract and parse a JSON object from an LLM response.

    Strategy:
    1) If a markdown code fence exists, parse its body.
       - If parsing fails, attempt to salvage by parsing from first '{' to last '}'.
    2) Otherwise, parse from first '{' to last '}' in the whole content.
    3) Finally, attempt to parse the whole content.
    """

    if not content or not content.strip():
        raise LLMJSONParseError("Content is empty")

    # 1) Prefer fenced JSON
    match = _CODE_FENCE_RE.search(content)
    if match:
        start_pos = match.end()
        end_pos = content.find("```", start_pos)
        json_str = content[start_pos:end_pos].strip() if end_pos != -1 else content[start_pos:].strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Salvage: parse the largest brace-delimited JSON object inside the fence.
            start_idx = json_str.find("{")
            end_idx = json_str.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                try:
                    return json.loads(json_str[start_idx : end_idx + 1])
                except json.JSONDecodeError as e:
                    raise LLMJSONParseError(f"Found code fence but failed to parse JSON: {e}") from e
            raise LLMJSONParseError("Found code fence but no JSON object could be extracted")

    # 2) Brace-delimited JSON in raw content
    start_idx = content.find("{")
    end_idx = content.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        try:
            return json.loads(content[start_idx : end_idx + 1])
        except json.JSONDecodeError:
            pass

    # 3) Last resort
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise LLMJSONParseError(f"Failed to parse JSON: {e}") from e
