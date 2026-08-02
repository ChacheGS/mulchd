"""
move_record tests — ownership, target-domain existence, and source-domain
auto-cleanup.
"""

import json

import pytest

from mulchd.models import RecordEvent, Role
from tests.mcp.conftest import ctx, _jot, _make_fake_move


async def test_move_relocates_record_between_domains(team, data_path, monkeypatch):
    """A successful move removes the record from the source domain's JSONL and
    appends it to the target domain's."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _move_record

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"
    record = _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="misplaced", owner="carlos",
    )
    _jot(
        data_path, "acme", "infra", "correct", type="convention",
        classification="foundational", content="existing target record", owner="carlos",
    )
    monkeypatch.setattr(mcp_tier2, "move_record", _make_fake_move(expertise))

    result = await _move_record(
        {"record_id": record["id"], "domain": "scratch", "target_domain": "correct"},
        ctx(t.carlos, t.org, t.infra),
    )

    assert f"Moved {record['id']} from scratch to correct" in result[0].text
    target_lines = (expertise / "correct.jsonl").read_text().splitlines()
    assert any(record["id"] in line for line in target_lines)


async def test_move_records_source_domain_on_the_event(team, data_path, monkeypatch):
    """The RecordEvent audit row captures where the record moved from, not just
    where it ended up — needed for the admin audit page to render the move."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _move_record

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"
    record = _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="misplaced", owner="carlos",
    )
    _jot(
        data_path, "acme", "infra", "correct", type="convention",
        classification="foundational", content="existing target record", owner="carlos",
    )
    monkeypatch.setattr(mcp_tier2, "move_record", _make_fake_move(expertise))

    await _move_record(
        {"record_id": record["id"], "domain": "scratch", "target_domain": "correct"},
        ctx(t.carlos, t.org, t.infra),
    )

    event = await RecordEvent.get(record_id=record["id"], action="move")
    assert event.source_domain == "scratch"
    assert event.domain == "correct"


async def test_move_last_record_removes_source_domain(team, data_path, monkeypatch):
    """Moving the only record out of a domain removes that domain's JSONL."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _move_record

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"
    record = _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="only record", owner="carlos",
    )
    _jot(
        data_path, "acme", "infra", "correct", type="convention",
        classification="foundational", content="existing target record", owner="carlos",
    )
    monkeypatch.setattr(mcp_tier2, "move_record", _make_fake_move(expertise))

    await _move_record(
        {"record_id": record["id"], "domain": "scratch", "target_domain": "correct"},
        ctx(t.carlos, t.org, t.infra),
    )

    assert not (expertise / "scratch.jsonl").exists()


async def test_move_non_last_record_preserves_source_domain(team, data_path, monkeypatch):
    """Moving one of several records leaves the source domain intact."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _move_record

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"
    record = _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="first", owner="carlos",
    )
    _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="second", owner="carlos",
    )
    _jot(
        data_path, "acme", "infra", "correct", type="convention",
        classification="foundational", content="existing target record", owner="carlos",
    )
    monkeypatch.setattr(mcp_tier2, "move_record", _make_fake_move(expertise))

    await _move_record(
        {"record_id": record["id"], "domain": "scratch", "target_domain": "correct"},
        ctx(t.carlos, t.org, t.infra),
    )

    assert (expertise / "scratch.jsonl").exists()


async def test_move_target_domain_must_already_exist(team, data_path):
    """Unlike write_* tools, move_record does not auto-create the target domain."""
    from mulchd.mcp.tier2 import _move_record

    t = team
    record = _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="v1", owner="carlos",
    )

    with pytest.raises(ValueError, match="target domain 'nonexistent' does not exist"):
        await _move_record(
            {"record_id": record["id"], "domain": "scratch", "target_domain": "nonexistent"},
            ctx(t.carlos, t.org, t.infra),
        )


async def test_move_source_equals_target_rejected(team, data_path):
    from mulchd.mcp.tier2 import _move_record

    t = team
    record = _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="v1", owner="carlos",
    )

    with pytest.raises(ValueError, match="source and target domain are the same"):
        await _move_record(
            {"record_id": record["id"], "domain": "scratch", "target_domain": "scratch"},
            ctx(t.carlos, t.org, t.infra),
        )


async def test_move_non_owner_writer_rejected(team, data_path):
    """Writers may only move their own records — same rule as edit_record."""
    from mulchd.mcp.tier2 import _move_record

    t = team
    record = _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="v1", owner="carlos",
    )
    _jot(
        data_path, "acme", "infra", "correct", type="convention",
        classification="foundational", content="existing target record", owner="carlos",
    )

    with pytest.raises(ValueError, match="you can only move your own records"):
        await _move_record(
            {"record_id": record["id"], "domain": "scratch", "target_domain": "correct"},
            ctx(t.jorge, t.org, t.infra),
        )


async def test_move_admin_can_move_any_record(team, data_path, monkeypatch):
    """Admins bypass the ownership check, mirroring edit_record/delete_record."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _move_record

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"
    record = _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="v1", owner="carlos",
    )
    _jot(
        data_path, "acme", "infra", "correct", type="convention",
        classification="foundational", content="existing target record", owner="carlos",
    )
    monkeypatch.setattr(mcp_tier2, "move_record", _make_fake_move(expertise))

    result = await _move_record(
        {"record_id": record["id"], "domain": "scratch", "target_domain": "correct"},
        ctx(t.jorge, t.org, t.infra, role=Role.ADMIN),
    )

    assert f"Moved {record['id']} from scratch to correct" in result[0].text


async def test_move_reader_role_rejected(team, data_path):
    from mulchd.mcp.tier2 import _move_record

    t = team
    record = _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="v1", owner="carlos",
    )

    with pytest.raises(ValueError, match="reader role cannot move records"):
        await _move_record(
            {"record_id": record["id"], "domain": "scratch", "target_domain": "correct"},
            ctx(t.carlos, t.org, t.infra, role=Role.READER),
        )


async def test_move_reports_incoming_references_same_domain(team, data_path, monkeypatch):
    """The response surfaces inbound relates_to/supersedes references, computed
    directly from the project's records rather than trusted from ml's move
    output — ml 0.10.7's own incomingReferences skips the entire source-domain
    file, so a referencer living in the *same* domain as the moved record
    (the case this test covers) would otherwise be silently missed."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _move_record

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"
    record = _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="v1", owner="carlos",
    )
    _jot(
        data_path, "acme", "infra", "scratch", type="decision",
        classification="tactical", title="refers to v1", rationale="see v1",
        relates_to=[record["id"]], owner="carlos",
    )
    _jot(
        data_path, "acme", "infra", "correct", type="convention",
        classification="foundational", content="existing target record", owner="carlos",
    )
    monkeypatch.setattr(mcp_tier2, "move_record", _make_fake_move(expertise))

    result = await _move_record(
        {"record_id": record["id"], "domain": "scratch", "target_domain": "correct"},
        ctx(t.carlos, t.org, t.infra),
    )

    assert "1 inbound reference(s) found" in result[0].text


async def test_move_rolls_back_jsonl_when_db_event_fails(team, data_path, monkeypatch):
    """If the RecordEvent row fails after the JSONL move already succeeded, the
    record must be moved back so the operation fails cleanly instead of leaving
    an untracked location change."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _move_record

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"
    record = _jot(
        data_path, "acme", "infra", "scratch", type="convention",
        classification="foundational", content="v1", owner="carlos",
    )
    _jot(
        data_path, "acme", "infra", "correct", type="convention",
        classification="foundational", content="existing target record", owner="carlos",
    )
    monkeypatch.setattr(mcp_tier2, "move_record", _make_fake_move(expertise))

    async def _fail(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(mcp_tier2.RecordEvent, "create", _fail)

    with pytest.raises(RuntimeError, match="db unavailable"):
        await _move_record(
            {"record_id": record["id"], "domain": "scratch", "target_domain": "correct"},
            ctx(t.carlos, t.org, t.infra),
        )

    source_lines = (expertise / "scratch.jsonl").read_text().splitlines()
    assert any(record["id"] in line for line in source_lines)
    target_lines = (expertise / "correct.jsonl").read_text().splitlines()
    assert not any(record["id"] in line for line in target_lines)
