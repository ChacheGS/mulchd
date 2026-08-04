"""
edit_record tests, including _annotate_edits.
"""

import pytest
import uuid
from mulchd.models import RecordEdit
from tests.mcp.conftest import ctx, _jot


async def test_edit_confirmation_names_org_and_project(team, data_path, fake_write_record):
    """The response stamps which org/project the edit happened in, so an
    agent juggling multiple mulchd connections can catch a wrong-target call."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record

    t = team

    await mcp_tier2._record_expertise(
        {
            "domain": "stamp-test",
            "type": "convention",
            "classification": "tactical",
            "content": "original",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise(
        {"domains": ["stamp-test"]}, ctx(t.carlos, t.org, t.infra)
    )
    record_id = records[1]["records"][0]["id"]

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    try:
        result = await _edit_record(
            {"record_id": record_id, "domain": "stamp-test", "content": "updated"},
            ctx(t.carlos, t.org, t.infra),
        )
    finally:
        mcp_tier2.edit_record = orig_edit

    assert "acme/infra" in result[0].text


async def test_edit_record_snapshots_before_values(team, data_path, fake_write_record):
    """RecordEdit captures the pre-edit values of changed fields."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record
    from mulchd.models import RecordEdit

    t = team

    await mcp_tier2._record_expertise(
        {
            "domain": "snap-test",
            "type": "convention",
            "classification": "tactical",
            "content": "original",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise(
        {"domains": ["snap-test"]}, ctx(t.carlos, t.org, t.infra)
    )
    record_id = records[1]["records"][0]["id"]

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    await _edit_record(
        {"record_id": record_id, "domain": "snap-test", "content": "updated"},
        ctx(t.carlos, t.org, t.infra),
    )
    mcp_tier2.edit_record = orig_edit

    edit = await RecordEdit.filter(record_id=record_id).first()
    assert edit is not None
    assert edit.before_snapshot == {"content": "original"}


async def test_edit_record_rejects_fabricated_supersedes(team, data_path, fake_write_record):
    """edit_record's supersedes update is validated the same way write is."""
    from mulchd.mcp.tier2 import _edit_record

    t = team
    r = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="v1", owner="carlos",
    )
    with pytest.raises(ValueError, match="supersedes references records that don't exist: mx-ghost"):
        await _edit_record(
            {"record_id": r["id"], "domain": "infra", "supersedes": ["mx-ghost"]},
            ctx(t.carlos, t.org, t.infra),
        )


async def test_edit_record_rejects_self_reference(team, data_path, fake_write_record):
    """A record cannot be edited to supersede or relate to itself."""
    from mulchd.mcp.tier2 import _edit_record

    t = team
    r = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="v1", owner="carlos",
    )
    with pytest.raises(ValueError, match="supersedes cannot reference the record's own id"):
        await _edit_record(
            {"record_id": r["id"], "domain": "infra", "supersedes": [r["id"]]},
            ctx(t.carlos, t.org, t.infra),
        )


async def test_edit_record_rejects_relates_to_self_reference(team, data_path, fake_write_record):
    """The self-reference guard applies to relates_to too, not just supersedes —
    _validate_references' loop is field-agnostic."""
    from mulchd.mcp.tier2 import _edit_record

    t = team
    r = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="v1", owner="carlos",
    )
    with pytest.raises(ValueError, match="relates_to cannot reference the record's own id"):
        await _edit_record(
            {"record_id": r["id"], "domain": "infra", "relates_to": [r["id"]]},
            ctx(t.carlos, t.org, t.infra),
        )


async def test_edit_record_content_only_skips_reference_validation(team, data_path, monkeypatch, fake_write_record):
    """Editing a field other than supersedes/relates_to must not trigger a
    project-wide scan at all — get_project_records should not be called."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record

    t = team
    r = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="v1", owner="carlos",
    )

    called = False
    original = mcp_tier2.get_project_records

    async def _tracking(*a, **kw):
        nonlocal called
        called = True
        return await original(*a, **kw)

    monkeypatch.setattr(mcp_tier2, "get_project_records", _tracking)

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    try:
        await _edit_record(
            {"record_id": r["id"], "domain": "infra", "content": "v2"},
            ctx(t.carlos, t.org, t.infra),
        )
    finally:
        mcp_tier2.edit_record = orig_edit
    assert called is False


async def test_edit_record_classification_downgrade_warning(team, data_path, fake_write_record):
    """edit_record response includes CLASSIFICATION DOWNGRADE when classification is lowered."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record

    t = team

    await mcp_tier2._record_expertise(
        {"domain": "api", "type": "convention", "classification": "foundational", "content": "v1"},
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise({"domains": ["api"]}, ctx(t.carlos, t.org, t.infra))
    record_id = records[1]["records"][0]["id"]

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    result = await _edit_record(
        {"record_id": record_id, "domain": "api", "classification": "tactical"},
        ctx(t.carlos, t.org, t.infra),
    )
    mcp_tier2.edit_record = orig_edit

    assert "CLASSIFICATION DOWNGRADE" in result[0].text
    assert "foundational" in result[0].text
    assert "tactical" in result[0].text


async def test_edit_record_supersession_warning_on_new_foundational_target(
    team, data_path, fake_write_record
):
    """Adding a supersedes reference to a foundational record via edit_record
    fires the same SUPERSESSION WARNING a write would — today it fires nothing."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record

    t = team
    foundational = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="foundational", content="Guardrail", owner="carlos",
    )
    await mcp_tier2._record_expertise(
        {"domain": "api", "type": "convention", "classification": "tactical", "content": "v1"},
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise({"domains": ["api"]}, ctx(t.carlos, t.org, t.infra))
    editable_id = [r["id"] for r in records[1]["records"] if r["id"] != foundational["id"]][0]

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    result = await _edit_record(
        {"record_id": editable_id, "domain": "api", "supersedes": [foundational["id"]]},
        ctx(t.carlos, t.org, t.infra),
    )
    mcp_tier2.edit_record = orig_edit

    text = result[0].text
    assert "SUPERSESSION WARNING" in text
    assert foundational["id"] in text
    assert "foundational → tactical" in text


async def test_edit_record_no_duplicate_warning_for_already_present_supersedes(
    team, data_path, fake_write_record
):
    """Re-submitting a supersedes list that already contained the foundational
    target (no new IDs added) must not warn again."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record

    t = team
    foundational = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="foundational", content="Guardrail", owner="carlos",
    )
    await mcp_tier2._record_expertise(
        {
            "domain": "api",
            "type": "convention",
            "classification": "tactical",
            "content": "v1",
            "supersedes": [foundational["id"]],
        },
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise({"domains": ["api"]}, ctx(t.carlos, t.org, t.infra))
    editable_id = [r["id"] for r in records[1]["records"] if r["id"] != foundational["id"]][0]

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    result = await _edit_record(
        {
            "record_id": editable_id,
            "domain": "api",
            "supersedes": [foundational["id"]],
            "content": "v2",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    mcp_tier2.edit_record = orig_edit

    assert "SUPERSESSION WARNING" not in result[0].text


async def test_edit_record_supersession_warning_uses_effective_classification(
    team, data_path, fake_write_record
):
    """When an edit changes classification and supersedes in the same call, the
    alert must compare against the NEW classification, not the record's stored one."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record

    t = team
    foundational = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="foundational", content="Guardrail", owner="carlos",
    )
    await mcp_tier2._record_expertise(
        {"domain": "api", "type": "convention", "classification": "foundational", "content": "v1"},
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise({"domains": ["api"]}, ctx(t.carlos, t.org, t.infra))
    editable_id = [r["id"] for r in records[1]["records"] if r["id"] != foundational["id"]][0]

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    result = await _edit_record(
        {
            "record_id": editable_id,
            "domain": "api",
            "classification": "observational",
            "supersedes": [foundational["id"]],
        },
        ctx(t.carlos, t.org, t.infra),
    )
    mcp_tier2.edit_record = orig_edit

    text = result[0].text
    assert "SUPERSESSION WARNING" in text
    assert "foundational → observational" in text


async def test_edit_record_outcome_stale_advisory_on_content_change(team, data_path, fake_write_record):
    """Editing a content field on a record with existing outcomes appends
    the OUTCOME TRUST STALE advisory."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record

    t = team
    r = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="v1", owner="carlos",
        outcomes=[
            {"status": "success", "recorded_at": "2026-07-28T00:00:00+00:00"},
            {"status": "success", "recorded_at": "2026-07-28T00:01:00+00:00"},
        ],
    )

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    try:
        result = await _edit_record(
            {"record_id": r["id"], "domain": "api", "content": "v2"},
            ctx(t.carlos, t.org, t.infra),
        )
    finally:
        mcp_tier2.edit_record = orig_edit

    assert "OUTCOME TRUST STALE" in result[0].text
    assert "2 confirmed outcome(s)" in result[0].text


async def test_edit_record_no_stale_advisory_without_outcomes(team, data_path, fake_write_record):
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record

    t = team
    r = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="v1", owner="carlos",
    )

    async def _noop_edit(m_dir, domain, rid, updates):
        pass

    orig_edit = mcp_tier2.edit_record
    mcp_tier2.edit_record = _noop_edit
    try:
        result = await _edit_record(
            {"record_id": r["id"], "domain": "api", "content": "v2"},
            ctx(t.carlos, t.org, t.infra),
        )
    finally:
        mcp_tier2.edit_record = orig_edit

    assert "OUTCOME TRUST STALE" not in result[0].text


async def test_edit_record_no_stale_advisory_for_non_content_field(team, data_path, fake_write_record):
    """Changing only classification (not in _CONTENT_FIELD_KEYS) on a record
    with outcomes must not trigger the advisory."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record

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
        result = await _edit_record(
            {"record_id": r["id"], "domain": "api", "classification": "observational"},
            ctx(t.carlos, t.org, t.infra),
        )
    finally:
        mcp_tier2.edit_record = orig_edit

    assert "OUTCOME TRUST STALE" not in result[0].text


async def test_annotate_edits_sets_edited_flag(team, data_path):
    """_annotate_edits marks records that have RecordEdit rows with _edited and edit count."""
    from mulchd.mcp.tier2 import _annotate_edits

    t = team
    r = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="tactical",
        content="Some rule",
        owner="carlos",
    )
    await RecordEdit.create(
        record_id=r["id"],
        project=t.infra,
        domain="api",
        actor=t.carlos,
        before_snapshot={"content": "Old rule"},
        client="test",
        session_id=uuid.uuid4(),
    )
    records = [r.copy()]
    await _annotate_edits(records, t.infra.id)
    assert records[0].get("_edited") is True
    assert records[0].get("_edit_count") == 1
    assert records[0].get("_last_edited_by") == "Carlos G."


async def test_annotate_edits_counts_multiple_edits(team, data_path):
    """_annotate_edits counts each edit and records the last editor."""
    from mulchd.mcp.tier2 import _annotate_edits

    t = team
    r = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="tactical",
        content="v1",
        owner="carlos",
    )
    for _ in range(3):
        await RecordEdit.create(
            record_id=r["id"],
            project=t.infra,
            domain="api",
            actor=t.jorge,
            before_snapshot={"content": "v1"},
            client="test",
            session_id=uuid.uuid4(),
        )
    records = [r.copy()]
    await _annotate_edits(records, t.infra.id)
    assert records[0]["_edit_count"] == 3
    assert records[0]["_last_edited_by"] == "Jorge M."


async def test_edit_rolls_back_jsonl_when_db_event_fails(team, data_path, fake_write_record, monkeypatch):
    """If RecordEvent/RecordEdit creation fails after the JSONL edit already
    applied, the pre-edit values must be restored so the operation fails
    cleanly instead of leaving an untracked edit on disk."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _edit_record

    t = team
    await mcp_tier2._record_expertise(
        {
            "domain": "rollback-test",
            "type": "convention",
            "classification": "tactical",
            "content": "original",
        },
        ctx(t.carlos, t.org, t.infra),
    )
    records = await mcp_tier2._read_expertise(
        {"domains": ["rollback-test"]}, ctx(t.carlos, t.org, t.infra)
    )
    record_id = records[1]["records"][0]["id"]

    calls = []

    async def _fake_edit(m_dir, domain, rid, updates):
        calls.append(updates)

    async def _fail(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(mcp_tier2, "edit_record", _fake_edit)
    monkeypatch.setattr(mcp_tier2.RecordEvent, "create", _fail)

    with pytest.raises(RuntimeError, match="db unavailable"):
        await _edit_record(
            {"record_id": record_id, "domain": "rollback-test", "content": "updated"},
            ctx(t.carlos, t.org, t.infra),
        )

    assert calls == [{"content": "updated"}, {"content": "original"}]
