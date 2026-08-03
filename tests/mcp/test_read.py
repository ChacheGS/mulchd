"""
read_records tests not covered by a more specific concern file.
"""

from datetime import datetime, timezone

import pytest

from mulchd.mcp.tier2 import _read_expertise
from tests.mcp.conftest import ctx, _jot


async def test_read_records_rejects_path_traversal_domain(team, data_path):
    """A domain containing path segments must be rejected, not resolved onto disk —
    otherwise a caller could read another org/project's records via ../.. segments."""
    t = team
    with pytest.raises(ValueError, match="invalid domain"):
        await _read_expertise(
            {"domains": ["../../other-org/other-project/.mulch/expertise/secrets"]},
            ctx(t.carlos, t.org, t.infra),
        )


async def test_read_records_unknown_domain_warns(team, data_path):
    """read_records warns on unknown domains rather than silently returning empty."""
    t = team
    text_content, structured = await _read_expertise(
        {"domains": ["nonexistent-domain"]},
        ctx(t.carlos, t.org, t.infra),
    )
    assert "Unknown domain" in text_content[0].text
    assert "nonexistent-domain" in text_content[0].text


async def test_read_records_cursor_pagination(team, data_path):
    """Cursor-based pagination returns pages in recorded_at order with an opaque next_cursor."""
    import base64

    t = team
    for i in range(3):
        _jot(
            data_path,
            "acme",
            "infra",
            "infra",
            type="convention",
            classification="tactical",
            content=f"record {i}",
            owner="carlos",
            recorded_at=datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc),
        )

    _, s1 = await _read_expertise({"domains": ["infra"], "limit": 2}, ctx(t.carlos, t.org, t.infra))
    assert len(s1["records"]) == 2
    assert s1["truncated"] is True
    assert s1["next_cursor"] is not None
    # cursor must be opaque — not a raw ISO timestamp
    assert s1["next_cursor"] != s1["records"][-1].get("recorded_at")
    # must be valid base64
    base64.b64decode(s1["next_cursor"])
    assert s1["records"][0]["content"] == "record 0"
    assert s1["records"][1]["content"] == "record 1"

    _, s2 = await _read_expertise(
        {"domains": ["infra"], "limit": 2, "cursor": s1["next_cursor"]},
        ctx(t.carlos, t.org, t.infra),
    )
    assert len(s2["records"]) == 1
    assert s2["records"][0]["content"] == "record 2"
    assert s2["truncated"] is False
    assert s2["next_cursor"] is None


async def test_read_records_cursor_tiebreak_on_id(team, data_path):
    """Two records with identical timestamps are disambiguated by id so no record is skipped."""
    t = team
    ts = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="twin a",
        owner="carlos",
        recorded_at=ts,
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="twin b",
        owner="carlos",
        recorded_at=ts,
    )

    _, s1 = await _read_expertise({"domains": ["infra"], "limit": 1}, ctx(t.carlos, t.org, t.infra))
    assert s1["truncated"] is True

    _, s2 = await _read_expertise(
        {"domains": ["infra"], "limit": 1, "cursor": s1["next_cursor"]},
        ctx(t.carlos, t.org, t.infra),
    )
    assert len(s2["records"]) == 1
    # both records returned across two pages — no skip, no duplicate
    contents = {s1["records"][0]["content"], s2["records"][0]["content"]}
    assert contents == {"twin a", "twin b"}


async def test_read_records_since_paginates_newest_first(team, data_path):
    """Passing `since` sorts newest-first instead of oldest-first, and cursor
    pagination still walks forward through that order without skipping or
    repeating a record."""
    t = team
    since = datetime(2025, 12, 31, tzinfo=timezone.utc)
    for i in range(3):
        _jot(
            data_path,
            "acme",
            "infra",
            "infra",
            type="convention",
            classification="tactical",
            content=f"record {i}",
            owner="carlos",
            recorded_at=datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc),
        )

    _, s1 = await _read_expertise(
        {"since": since.isoformat(), "domains": ["infra"], "limit": 2},
        ctx(t.carlos, t.org, t.infra),
    )
    assert s1["truncated"] is True
    assert s1["records"][0]["content"] == "record 2"
    assert s1["records"][1]["content"] == "record 1"

    _, s2 = await _read_expertise(
        {"since": since.isoformat(), "domains": ["infra"], "limit": 2, "cursor": s1["next_cursor"]},
        ctx(t.carlos, t.org, t.infra),
    )
    assert s2["truncated"] is False
    assert s2["next_cursor"] is None
    assert [r["content"] for r in s2["records"]] == ["record 0"]


async def test_read_records_structured_truncation_flag(team, data_path):
    """read_records sets truncated=True when limit is hit."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="record one",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="record two",
        owner="carlos",
    )

    text_content, structured = await _read_expertise(
        {"domains": ["infra"], "limit": 1},
        ctx(t.carlos, t.org, t.infra),
    )
    assert structured["truncated"] is True
    assert len(structured["records"]) == 1

    text_content2, structured2 = await _read_expertise(
        {"domains": ["infra"], "limit": 10},
        ctx(t.carlos, t.org, t.infra),
    )
    assert structured2["truncated"] is False


async def test_read_records_unknown_domain_in_structured_output(team, data_path):
    """read_records should expose unknown domain names in structured output,
    not just as a text warning that structured clients may never see."""
    t = team
    _, structured = await _read_expertise(
        {"domains": ["does-not-exist"]},
        ctx(t.carlos, t.org, t.infra),
    )
    assert (
        "unknown_domains" in structured
    ), "structured output must include 'unknown_domains' when unrecognised names are requested"
    assert "does-not-exist" in structured["unknown_domains"]


async def test_cross_domain_hints_in_read_records(team, data_path):
    """read_records includes cross_domain_hints when a record is superseded from another domain."""
    t = team
    victim = _jot(
        data_path,
        "acme",
        "infra",
        "guardrails",
        type="convention",
        classification="foundational",
        content="Original guardrail",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "policies",
        type="convention",
        classification="foundational",
        content="Replacement",
        owner="carlos",
        supersedes=[victim["id"]],
    )

    # Read only the victim's domain
    _, structured = await _read_expertise(
        {"domains": ["guardrails"]}, ctx(t.carlos, t.org, t.infra)
    )
    hints = structured.get("cross_domain_hints", [])
    assert len(hints) == 1
    assert hints[0]["record_id"] == victim["id"]
    assert hints[0]["in_domain"] == "policies"
