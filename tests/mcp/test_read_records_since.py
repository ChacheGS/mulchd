"""
read_records(since=...) timestamp-filtering tests.
"""

import uuid
from datetime import datetime, timedelta, timezone

from mulchd.mcp.tier2 import _read_expertise
from mulchd.models import RecordMeta
from tests.mcp.conftest import _jot, ctx


async def test_read_records_since_excludes_old_records(team, data_path):
    """Records written before `since` are excluded; newer ones appear."""
    t = team
    old_ts = datetime.now(timezone.utc) - timedelta(hours=2)
    new_ts = datetime.now(timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="observational",
        content="Old practice — now superseded",
        owner="carlos",
        recorded_at=old_ts,
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="decision",
        classification="foundational",
        content="New decision post-migration",
        owner="jorge",
        recorded_at=new_ts,
    )

    text_content, _ = await _read_expertise(
        {"since": cutoff.isoformat(), "domains": ["infra"]},
        ctx(t.jorge, t.org, t.infra),
    )
    text = text_content[0].text
    assert "New decision post-migration" in text
    assert "Old practice" not in text


async def test_read_records_since_multiple_domains(team, data_path):
    """read_records(since=...) aggregates across domains when multiple are specified."""
    t = team
    since = datetime.now(timezone.utc) - timedelta(seconds=1)

    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="decision",
        classification="foundational",
        content="Infra domain record",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "governance",
        type="convention",
        classification="foundational",
        content="Governance domain record",
        owner="jorge",
    )

    text_content, _ = await _read_expertise(
        {"since": since.isoformat(), "domains": ["infra", "governance"]},
        ctx(t.carlos, t.org, t.infra),
    )
    text = text_content[0].text
    assert "Infra domain record" in text
    assert "Governance domain record" in text


async def test_read_records_since_defaults_to_all_domains(team, data_path):
    """Omitting `domains` while passing `since` scans every domain in the project,
    matching the old get_recent default."""
    t = team
    since = datetime.now(timezone.utc) - timedelta(seconds=1)

    _jot(
        data_path,
        "acme",
        "infra",
        "governance",
        type="convention",
        classification="foundational",
        content="Governance domain record",
        owner="jorge",
    )

    text_content, _ = await _read_expertise(
        {"since": since.isoformat()},
        ctx(t.carlos, t.org, t.infra),
    )
    assert "Governance domain record" in text_content[0].text


async def test_read_records_since_does_not_leak_attribution_across_projects_with_same_record_id(
    team, data_path
):
    """ml's record IDs are content-derived, not random, so two different
    projects can legitimately produce the same record_id (see RecordMeta's
    (project, record_id) unique_together). read_records(since=...) for one
    project must only ever see that project's RecordMeta row, never the
    other's author."""
    t = team
    dupe_id = "mx-dupe123"
    now = datetime.now(timezone.utc)

    # A RecordMeta row for the *other* project, same record_id, different author.
    await RecordMeta.create(
        record_id=dupe_id,
        project=t.data,
        domain="pipelines",
        author=t.ana,
        session_id=uuid.uuid4(),
        client="test",
    )
    # The row that actually belongs to the project under test.
    await RecordMeta.create(
        record_id=dupe_id,
        project=t.infra,
        domain="infra",
        author=t.carlos,
        session_id=uuid.uuid4(),
        client="test",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        id=dupe_id,
        type="decision",
        classification="foundational",
        content="Infra's record sharing an ID with a data-platform record",
        owner="carlos",
        recorded_at=now,
    )

    text_content, _ = await _read_expertise(
        {"since": (now - timedelta(seconds=1)).isoformat(), "domains": ["infra"]},
        ctx(t.carlos, t.org, t.infra),
    )
    text = text_content[0].text
    assert "Carlos G." in text
    assert "Ana R." not in text


async def test_read_records_since_structured_output_carries_session_grouping_key(
    team, data_path
):
    """The tool description promises since= results "grouped by the session
    that wrote them" — the text output delivers that via "## Session —" \
    headers, but structured_content's records list is flat with no field a
    caller could group by itself. Two distinct RecordMeta session_ids must
    show up as two distinct _session_id values on the matching records."""
    t = team
    now = datetime.now(timezone.utc)
    session_a = uuid.uuid4()
    session_b = uuid.uuid4()

    record_a = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="from session A",
        owner="carlos",
        recorded_at=now,
    )
    record_b = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="from session B",
        owner="jorge",
        recorded_at=now,
    )
    await RecordMeta.create(
        record_id=record_a["id"],
        project=t.infra,
        domain="infra",
        author=t.carlos,
        session_id=session_a,
        client="test",
    )
    await RecordMeta.create(
        record_id=record_b["id"],
        project=t.infra,
        domain="infra",
        author=t.jorge,
        session_id=session_b,
        client="test",
    )

    _, structured = await _read_expertise(
        {"since": (now - timedelta(seconds=1)).isoformat(), "domains": ["infra"]},
        ctx(t.carlos, t.org, t.infra),
    )
    by_id = {r["id"]: r for r in structured["records"]}
    assert by_id[record_a["id"]]["_session_id"] == str(session_a)
    assert by_id[record_b["id"]]["_session_id"] == str(session_b)
    assert by_id[record_a["id"]]["_session_id"] != by_id[record_b["id"]]["_session_id"]
