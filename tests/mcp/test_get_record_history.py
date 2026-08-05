"""
get_record_history tests.
"""

import uuid

from mulchd.models import RecordEdit, RecordEvent, Role
from tests.mcp.conftest import _jot, _make_fake_move, ctx


async def test_get_record_history_renders_write_edit_delete_timeline(
    team, data_path, fake_write_record
):
    """get_record_history shows the full write/edit/delete timeline in order,
    with actor and before_snapshot fields for edits."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record, _get_record_history

    t = team
    await mcp_tier2._record_expertise(
        {
            "domain": "history-test",
            "type": "convention",
            "classification": "foundational",
            "content": "Two-person sign-off required for all deletions.",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise(
        {"domains": ["history-test"]}, ctx(t.carlos, t.org, t.infra)
    )
    record_id = records[1]["records"][0]["id"]

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    await _edit_record(
        {
            "record_id": record_id,
            "domain": "history-test",
            "content": "Single-engineer discretion allowed for deletions.",
        },
        ctx(t.jorge, t.org, t.infra, role=Role.ADMIN),
    )
    mcp_tier2.edit_record = orig_edit

    result = await _get_record_history({"record_id": record_id}, ctx(t.carlos, t.org, t.infra))
    text = result[0].text

    assert f"History for {record_id}" in text
    assert "write" in text
    assert "carlos" in text or "Carlos" in text
    assert "edit" in text
    assert "jorge" in text or "Jorge" in text
    assert "Two-person sign-off required for all deletions." in text
    write_idx = text.index("write")
    edit_idx = text.index("edit")
    assert write_idx < edit_idx


async def test_get_record_history_renders_move_source_and_destination(
    team, data_path, monkeypatch
):
    """A move entry must show which domain the record came from and went to,
    not just "move by <actor>" — get_record_history is otherwise the only
    place an agent can see this without cross-referencing the JSONL files."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _get_record_history, _move_record

    t = team
    expertise = data_path / "acme" / "infra" / ".mulch" / "expertise"
    record = _jot(
        data_path,
        "acme",
        "infra",
        "scratch",
        type="convention",
        classification="foundational",
        content="misplaced",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "correct",
        type="convention",
        classification="foundational",
        content="existing target record",
        owner="carlos",
    )
    monkeypatch.setattr(mcp_tier2, "move_record", _make_fake_move(expertise))
    await _move_record(
        {"record_id": record["id"], "domain": "scratch", "target_domain": "correct"},
        ctx(t.carlos, t.org, t.infra),
    )

    result = await _get_record_history(
        {"record_id": record["id"]}, ctx(t.carlos, t.org, t.infra)
    )
    text = result[0].text
    assert "move" in text
    assert "scratch → correct" in text


async def test_get_record_history_move_with_no_source_domain_shows_placeholder(
    team, data_path
):
    """A legacy move row written before source_domain was tracked has it as
    NULL — rendering must not leak the literal Python "None" into user-facing
    text."""
    from mulchd.mcp.tier2 import _get_record_history

    t = team
    record = _jot(
        data_path,
        "acme",
        "infra",
        "architecture",
        type="convention",
        classification="tactical",
        content="moved in from somewhere untracked",
        owner="carlos",
    )
    await RecordEvent.create(
        record_id=record["id"],
        project=t.infra,
        domain="architecture",
        source_domain=None,
        actor=t.carlos,
        action="move",
        client="test",
    )

    result = await _get_record_history({"record_id": record["id"]}, ctx(t.carlos, t.org, t.infra))
    text = result[0].text
    assert "None → architecture" not in text
    assert "(unknown) → architecture" in text


async def test_get_record_history_no_history_found(team, data_path):
    """A record with zero RecordEvent rows returns a plain message, not an error."""
    from mulchd.mcp.tier2 import _get_record_history

    t = team
    result = await _get_record_history(
        {"record_id": "mx-neverexisted"}, ctx(t.carlos, t.org, t.infra)
    )
    assert "No history found for mx-neverexisted" in result[0].text
    # Names the org/project so an agent juggling multiple mulchd connections
    # can catch a lookup against the wrong target.
    assert "acme/infra" in result[0].text


async def test_get_record_history_matches_snapshots_by_session_not_position(team, data_path):
    """Two different actors editing the same record in overlapping sessions
    must not have their before_snapshots swapped just because RecordEvent's
    and RecordEdit's independent (at) orderings don't line up — snapshots are
    matched by session_id, mirroring admin/record_activity.py's approach."""
    import asyncio

    from mulchd.mcp.tier2 import _get_record_history

    t = team
    record_id = "mx-concurrent1"
    session_a = uuid.uuid4()
    session_b = uuid.uuid4()

    # RecordEvent order: carlos's edit (session_a) before jorge's edit (session_b).
    await RecordEvent.create(
        record_id=record_id,
        project=t.infra,
        domain="api",
        actor=t.carlos,
        action="edit",
        client="test",
        session_id=session_a,
    )
    await asyncio.sleep(0.01)
    await RecordEvent.create(
        record_id=record_id,
        project=t.infra,
        domain="api",
        actor=t.jorge,
        action="edit",
        client="test",
        session_id=session_b,
    )
    await asyncio.sleep(0.01)
    # RecordEdit order deliberately reversed relative to RecordEvent's (at):
    # jorge's (session_b) snapshot row is created — and so sorts — before
    # carlos's (session_a) one, even though carlos's edit event came first.
    await RecordEdit.create(
        record_id=record_id,
        project=t.infra,
        domain="api",
        actor=t.jorge,
        before_snapshot={"content": "jorge-old"},
        client="test",
        session_id=session_b,
    )
    await asyncio.sleep(0.01)
    await RecordEdit.create(
        record_id=record_id,
        project=t.infra,
        domain="api",
        actor=t.carlos,
        before_snapshot={"content": "carlos-old"},
        client="test",
        session_id=session_a,
    )

    result = await _get_record_history({"record_id": record_id}, ctx(t.carlos, t.org, t.infra))
    text = result[0].text

    carlos_line_idx = text.index("by Carlos G.")
    jorge_line_idx = text.index("by Jorge M.")
    carlos_snapshot_idx = text.index("carlos-old")
    jorge_snapshot_idx = text.index("jorge-old")
    # carlos's snapshot must follow carlos's line (and precede jorge's line);
    # a naive positional zip would instead attach jorge-old to carlos's line.
    assert carlos_line_idx < carlos_snapshot_idx < jorge_line_idx < jorge_snapshot_idx


async def test_get_record_history_reader_role_can_call(team, data_path, fake_write_record):
    """get_record_history is read-only and available to READER role too."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _get_record_history

    t = team
    await mcp_tier2._record_expertise(
        {
            "domain": "history-test",
            "type": "convention",
            "classification": "tactical",
            "content": "v1",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise(
        {"domains": ["history-test"]}, ctx(t.carlos, t.org, t.infra)
    )
    record_id = records[1]["records"][0]["id"]

    result = await _get_record_history(
        {"record_id": record_id}, ctx(t.carlos, t.org, t.infra, role=Role.READER)
    )
    assert f"History for {record_id}" in result[0].text
