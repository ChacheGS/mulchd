"""
Tests for _get_record_schema — previously had zero coverage anywhere in the
suite (found during a coverage audit, 2026-07-29). Pure formatting over the
static _RECORD_SCHEMAS dict, no ctx/db/ml needed.
"""


async def test_get_record_schema_no_filter_lists_all_types():
    from mulchd.mcp.tier2 import _get_record_schema

    result = await _get_record_schema({})
    text = result[0].text
    for rtype in ("convention", "decision", "failure", "pattern", "reference", "guide"):
        assert f"**{rtype}**" in text


async def test_get_record_schema_filtered_to_one_type():
    from mulchd.mcp.tier2 import _get_record_schema

    result = await _get_record_schema({"type": "decision"})
    text = result[0].text
    assert "**decision**" in text
    assert "**convention**" not in text
    assert "**failure**" not in text


async def test_get_record_schema_shows_required_fields():
    from mulchd.mcp.tier2 import _get_record_schema

    result = await _get_record_schema({"type": "failure"})
    text = result[0].text
    assert "`description`" in text
    assert "`resolution`" in text


async def test_get_record_schema_shows_optional_fields_when_present():
    from mulchd.mcp.tier2 import _get_record_schema

    result = await _get_record_schema({"type": "decision"})
    text = result[0].text
    assert "optional:" in text
    assert "`date`" in text


async def test_get_record_schema_omits_optional_line_when_none():
    """convention has no optional fields at all — the 'optional:' line
    should be skipped entirely for it, not printed empty."""
    from mulchd.mcp.tier2 import _get_record_schema

    result = await _get_record_schema({"type": "convention"})
    text = result[0].text
    # isolate convention's own block to avoid matching another type's optional line
    block = text.split("**convention**", 1)[1].split("**", 1)[0]
    assert "optional:" not in block


async def test_get_record_schema_required_none_when_no_required_fields():
    """Every real type has required fields today, but the 'none' fallback
    text (schema['required'] empty) is part of the function's contract —
    exercise it directly against a type with no required fields."""
    from mulchd.mcp import tier2

    original = tier2._RECORD_SCHEMAS
    try:
        tier2._RECORD_SCHEMAS = {**original, "guide": {"required": {}, "optional": {}}}
        result = await tier2._get_record_schema({"type": "guide"})
        text = result[0].text
        assert "required: none" in text
    finally:
        tier2._RECORD_SCHEMAS = original
