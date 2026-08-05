"""
relates_to read-time display tests (mark_related_to) and move_record's
independently-computed incoming-reference count (find_incoming_references).
"""

import json

from mulchd.mcp.tier2 import _read_expertise
from tests.mcp.conftest import _jot, ctx


async def test_mark_related_to_sets_outgoing_and_incoming_tags(team, data_path):
    """B relates_to A: A gets _related_by, B gets _relates_to_display."""
    from mulchd.mcp.tier2 import mark_related_to

    t = team
    a = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="A",
        owner="carlos",
    )
    b = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="B",
        owner="carlos",
        relates_to=[a["id"]],
    )
    a["_domain"] = "infra"
    b["_domain"] = "infra"
    records = [a, b]
    await mark_related_to(records, "acme", "infra")

    assert records[0]["_related_by"] == [b["id"]]
    assert records[1]["_relates_to_display"] == [a["id"]]


async def test_mark_related_to_incoming_collects_multiple_referencers(team, data_path):
    """Unlike supersedes' _superseded_by (single winner), relates_to's
    incoming side collects every referencer, since it's a non-exclusive
    association."""
    from mulchd.mcp.tier2 import mark_related_to

    t = team
    a = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="A",
        owner="carlos",
    )
    b = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="B",
        owner="carlos",
        relates_to=[a["id"]],
    )
    c = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="C",
        owner="carlos",
        relates_to=[a["id"]],
    )
    a["_domain"] = "infra"
    records = [a]
    await mark_related_to(records, "acme", "infra")

    assert sorted(records[0]["_related_by"]) == sorted([b["id"], c["id"]])


async def test_mark_related_to_labels_deleted_target(team, data_path):
    from mulchd.domains import mulch_dir
    from mulchd.mcp.tier2 import mark_related_to

    t = team
    m_dir = mulch_dir("acme", "infra")
    archive_dir = m_dir / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "infra.jsonl").write_text(
        json.dumps({"id": "mx-archived1", "type": "convention", "classification": "tactical"})
        + "\n"
    )
    new = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="New",
        owner="carlos",
        relates_to=["mx-archived1"],
    )
    new["_domain"] = "infra"
    records = [new]
    await mark_related_to(records, "acme", "infra")

    assert records[0]["_relates_to_display"] == ["mx-archived1 (deleted)"]


async def test_mark_related_to_labels_missing_target(team, data_path):
    from mulchd.mcp.tier2 import mark_related_to

    t = team
    new = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="New",
        owner="carlos",
        relates_to=["mx-never-existed"],
    )
    new["_domain"] = "infra"
    records = [new]
    await mark_related_to(records, "acme", "infra")

    assert records[0]["_relates_to_display"] == ["mx-never-existed (missing)"]


async def test_read_records_renders_relates_to_on_both_sides(team, data_path):
    """When record B relates_to record A, both A and B show the link in
    text output — this was the reported gap: relates_to had write-time
    validation but zero read-time display."""
    t = team
    a = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="Record A",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="Record B",
        owner="carlos",
        relates_to=[a["id"]],
    )

    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra)
    )
    text = text_content[0].text
    b_record = next(r for r in structured["records"] if r.get("relates_to"))
    assert f"relates to {a['id']}" in text
    assert f"referenced by {b_record['id']}" in text
