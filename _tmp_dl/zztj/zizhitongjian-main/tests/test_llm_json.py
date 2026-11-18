from zztj_pipeline.llm_json import extract_json_from_response, LLMJSONParseError


def test_extract_from_json_fence():
    content = """```json
{\n  \"a\": 1, \"b\": {\"c\": 2}\n}
```"""
    assert extract_json_from_response(content) == {"a": 1, "b": {"c": 2}}


def test_extract_from_fence_with_trailing_text():
    content = """```json
{\n  \"a\": 1\n}
```
some trailing commentary"""
    assert extract_json_from_response(content) == {"a": 1}


def test_extract_from_braces_without_fence():
    content = "prefix... {\"a\": 1, \"b\": 2} ...suffix"
    assert extract_json_from_response(content) == {"a": 1, "b": 2}


def test_extract_salvage_inside_fence():
    # Missing closing fence; still should salvage the JSON object
    content = """```json
{\n  \"a\": 1\n}
"""
    assert extract_json_from_response(content) == {"a": 1}


def test_empty_content_raises():
    try:
        extract_json_from_response("   ")
    except LLMJSONParseError:
        return
    assert False, "Expected LLMJSONParseError"
