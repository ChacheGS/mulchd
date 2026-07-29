"""
record_outcome, outcome tag formatting, and staleness annotation tests.
"""

import json
import pytest
import uuid
from datetime import datetime, timezone
from mulchd.models import Role
from mulchd.mcp.tier2 import _read_expertise
from tests.mcp.conftest import ctx, _jot


async def test_record_outcome_creates_visible_outcome(team, data_path, fake_write_record):
    """record_outcome appends an outcome visible on a subsequent read, and
    returns a confirmation naming the status."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _record_outcome

    t = team
    await mcp_tier2._record_expertise(
        {"domain": "infra", "type": "convention", "classification": "tactical", "content": "v1"},
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    record_id = records[1]["records"][0]["id"]

    async def _fake_outcome(m_dir, domain, rid, status, notes=None):
        path = m_dir / "expertise" / f"{domain}.jsonl"
        lines = path.read_text().splitlines()
        rewritten = []
        for line in lines:
            rec = json.loads(line)
            if rec.get("id") == rid:
                rec.setdefault("outcomes", []).append(
                    {
                        "status": status.value,
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                        "notes": notes,
                    }
                )
            rewritten.append(json.dumps(rec))
        path.write_text("\n".join(rewritten) + "\n")
        return {"success": True}

    orig = mcp_tier2.record_outcome
    mcp_tier2.record_outcome = _fake_outcome
    try:
        result = await _record_outcome(
            {"record_id": record_id, "domain": "infra", "status": "success", "notes": "worked great"},
            ctx(t.carlos, t.org, t.infra),
        )
    finally:
        mcp_tier2.record_outcome = orig

    assert f"Recorded success outcome for {record_id}" in result[0].text
    records2 = await mcp_tier2._read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    outcomes = records2[1]["records"][0]["outcomes"]
    assert outcomes[0]["status"] == "success"
    assert outcomes[0]["notes"] == "worked great"


async def test_record_outcome_non_owner_writer_allowed(team, data_path, fake_write_record):
    """Unlike edit_record, any WRITER can record an outcome on someone else's
    record — confirming whether guidance worked isn't restricted to its author."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _record_outcome

    t = team
    await mcp_tier2._record_expertise(
        {"domain": "infra", "type": "convention", "classification": "tactical", "content": "v1"},
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    record_id = records[1]["records"][0]["id"]
    assert records[1]["records"][0]["owner"] == "carlos"

    async def _fake_outcome(m_dir, domain, rid, status, notes=None):
        return {"success": True}

    orig = mcp_tier2.record_outcome
    mcp_tier2.record_outcome = _fake_outcome
    try:
        result = await _record_outcome(
            {"record_id": record_id, "domain": "infra", "status": "failure"},
            ctx(t.jorge, t.org, t.infra),
        )
    finally:
        mcp_tier2.record_outcome = orig

    assert f"Recorded failure outcome for {record_id}" in result[0].text


async def test_record_outcome_reader_role_rejected(team, data_path, fake_write_record):
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _record_outcome

    t = team
    await mcp_tier2._record_expertise(
        {"domain": "infra", "type": "convention", "classification": "tactical", "content": "v1"},
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    record_id = records[1]["records"][0]["id"]

    with pytest.raises(ValueError, match="reader role cannot record outcomes"):
        await _record_outcome(
            {"record_id": record_id, "domain": "infra", "status": "success"},
            ctx(t.carlos, t.org, t.infra, role=Role.READER),
        )


async def test_record_outcome_record_not_found(team, data_path):
    from mulchd.mcp.tier2 import _record_outcome

    t = team
    with pytest.raises(ValueError, match="record mx-ghost not found in domain infra"):
        await _record_outcome(
            {"record_id": "mx-ghost", "domain": "infra", "status": "success"},
            ctx(t.carlos, t.org, t.infra),
        )


def test_format_outcomes_tag_single_status():
    from mulchd.mcp.tier2 import _format_outcomes_tag

    r = {"outcomes": [{"status": "success", "recorded_at": "2026-07-28T00:00:00+00:00"}]}
    assert _format_outcomes_tag(r) == " • ✓ 1 success"


def test_format_outcomes_tag_mixed_statuses_fixed_order():
    from mulchd.mcp.tier2 import _format_outcomes_tag

    r = {
        "outcomes": [
            {"status": "failure", "recorded_at": "2026-07-28T00:00:00+00:00"},
            {"status": "success", "recorded_at": "2026-07-28T00:01:00+00:00"},
            {"status": "success", "recorded_at": "2026-07-28T00:02:00+00:00"},
            {"status": "partial", "recorded_at": "2026-07-28T00:03:00+00:00"},
        ]
    }
    assert _format_outcomes_tag(r) == " • ✓ 2 success, 1 partial, 1 failure"


def test_format_outcomes_tag_empty():
    from mulchd.mcp.tier2 import _format_outcomes_tag

    assert _format_outcomes_tag({}) == ""
    assert _format_outcomes_tag({"outcomes": []}) == ""


async def test_annotate_outcome_staleness_flags_edit_after_outcome(team, data_path):
    from mulchd.mcp.tier2 import _annotate_outcome_staleness
    from mulchd.models import RecordEdit

    t = team
    r = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="v2", owner="carlos",
        outcomes=[{"status": "success", "recorded_at": "2026-07-28T00:00:00+00:00"}],
    )
    await RecordEdit.create(
        record_id=r["id"], project=t.infra, domain="api", actor=t.carlos,
        before_snapshot={"content": "v1"}, client="test", session_id=uuid.uuid4(),
    )
    records = [r.copy()]
    await _annotate_outcome_staleness(records, t.infra.id)
    assert records[0].get("_outcomes_stale") is True


async def test_annotate_outcome_staleness_handles_z_suffix_timestamp(team, data_path):
    """A real ml-produced outcome timestamp isn't guaranteed to use Python's
    own +00:00 offset style — Z-suffix ISO 8601 must parse and compare
    correctly too, not just the format Python happens to emit."""
    from mulchd.mcp.tier2 import _annotate_outcome_staleness
    from mulchd.models import RecordEdit

    t = team
    r = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="v2", owner="carlos",
        outcomes=[{"status": "success", "recorded_at": "2026-07-28T00:00:00Z"}],
    )
    await RecordEdit.create(
        record_id=r["id"], project=t.infra, domain="api", actor=t.carlos,
        before_snapshot={"content": "v1"}, client="test", session_id=uuid.uuid4(),
        at=datetime(2026, 7, 28, 0, 0, 1, tzinfo=timezone.utc),
    )
    records = [r.copy()]
    await _annotate_outcome_staleness(records, t.infra.id)
    assert records[0].get("_outcomes_stale") is True


async def test_annotate_outcome_staleness_not_flagged_when_outcome_is_newer(team, data_path):
    """A fresh outcome recorded after the edit means the content has since
    been re-confirmed — not stale."""
    from mulchd.mcp.tier2 import _annotate_outcome_staleness
    from mulchd.models import RecordEdit

    t = team
    r = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="v2", owner="carlos",
        outcomes=[{"status": "success", "recorded_at": "2026-07-28T23:59:59+00:00"}],
    )
    await RecordEdit.create(
        record_id=r["id"], project=t.infra, domain="api", actor=t.carlos,
        before_snapshot={"content": "v1"}, client="test", session_id=uuid.uuid4(),
        at=datetime(2026, 7, 28, 0, 0, tzinfo=timezone.utc),
    )
    records = [r.copy()]
    await _annotate_outcome_staleness(records, t.infra.id)
    assert records[0].get("_outcomes_stale") is None


async def test_annotate_outcome_staleness_ignores_non_content_edits(team, data_path):
    """An edit that only touched classification/supersedes (not a content
    field) must not trigger staleness even if it postdates the outcome."""
    from mulchd.mcp.tier2 import _annotate_outcome_staleness
    from mulchd.models import RecordEdit

    t = team
    r = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="v1", owner="carlos",
        outcomes=[{"status": "success", "recorded_at": "2026-07-28T00:00:00+00:00"}],
    )
    await RecordEdit.create(
        record_id=r["id"], project=t.infra, domain="api", actor=t.carlos,
        before_snapshot={"classification": "observational"}, client="test", session_id=uuid.uuid4(),
    )
    records = [r.copy()]
    await _annotate_outcome_staleness(records, t.infra.id)
    assert records[0].get("_outcomes_stale") is None


async def test_annotate_outcome_staleness_skips_records_without_outcomes(team, data_path):
    from mulchd.mcp.tier2 import _annotate_outcome_staleness
    from mulchd.models import RecordEdit

    t = team
    r = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="v2", owner="carlos",
    )
    await RecordEdit.create(
        record_id=r["id"], project=t.infra, domain="api", actor=t.carlos,
        before_snapshot={"content": "v1"}, client="test", session_id=uuid.uuid4(),
    )
    records = [r.copy()]
    await _annotate_outcome_staleness(records, t.infra.id)
    assert records[0].get("_outcomes_stale") is None


async def test_edit_then_self_confirm_clears_stale_flag(team, data_path, fake_write_record):
    """Known, accepted limitation (see _annotate_outcome_staleness's
    docstring): record_outcome has no ownership check by design, so whoever
    just edited a record's content can immediately re-confirm it themselves
    and clear the stale flag before anyone else reads it. This is detection,
    not prevention — ml gives no way to make it a hard gate — so this test
    pins the limitation as understood behavior rather than a silent gap."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _annotate_outcome_staleness, _edit_record, _record_outcome

    t = team
    r = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="v1", owner="carlos",
        outcomes=[{"status": "success", "recorded_at": "2026-07-28T00:00:00+00:00"}],
    )

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    try:
        await _edit_record(
            {"record_id": r["id"], "domain": "api", "content": "v2 (attacker-controlled)"},
            ctx(t.carlos, t.org, t.infra),
        )
    finally:
        mcp_tier2.edit_record = orig_edit

    # Without a fresh confirmation, the edit alone would already flag stale.
    stale_check = r.copy()
    await _annotate_outcome_staleness([stale_check], t.infra.id)
    assert stale_check.get("_outcomes_stale") is True

    async def _fake_outcome(m_dir, domain, rid, status, notes=None):
        r["outcomes"].append(
            {
                "status": status.value,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "notes": notes,
            }
        )
        return {"success": True}

    orig_outcome = mcp_tier2.record_outcome
    mcp_tier2.record_outcome = _fake_outcome
    try:
        await _record_outcome(
            {"record_id": r["id"], "domain": "api", "status": "success"},
            ctx(t.carlos, t.org, t.infra),
        )
    finally:
        mcp_tier2.record_outcome = orig_outcome

    cleared_check = r.copy()
    await _annotate_outcome_staleness([cleared_check], t.infra.id)
    assert cleared_check.get("_outcomes_stale") is None


def test_format_outcomes_tag_stale_suffix():
    from mulchd.mcp.tier2 import _format_outcomes_tag

    r = {
        "outcomes": [{"status": "success", "recorded_at": "2026-07-28T00:00:00+00:00"}],
        "_outcomes_stale": True,
    }
    assert _format_outcomes_tag(r) == " • ✓ 1 success ⚠ stale (edited since last confirmed)"


async def test_read_records_renders_outcomes_tag(team, data_path):
    """A record seeded directly into JSONL with outcomes (legacy-data path,
    same as this session's other fixture-based tests) renders the tag on
    read without ever going through record_outcome itself."""
    t = team
    _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="v1", owner="carlos",
        outcomes=[{"status": "success", "recorded_at": "2026-07-28T00:00:00+00:00"}],
    )
    text_content, _ = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    assert "✓ 1 success" in text_content[0].text
