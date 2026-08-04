"""
Supersession, reference validation, and cycle-detection tests (mark_superseded, _find_cycles, validate_references).
"""

import json
import pytest
from mulchd.mcp.tier2 import _read_expertise
from tests.mcp.conftest import ctx, _jot


async def test_supersede_alerts_foundational_same_tier(team, data_path):
    """supersede_alerts fires when a foundational record is superseded, even at the same tier."""
    from mulchd.domains import mulch_dir
    from mulchd.mcp.tier2 import supersede_alerts

    t = team
    r = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="foundational",
        content="Guardrail",
        owner="carlos",
    )
    alerts = await supersede_alerts(mulch_dir("acme", "infra"), [r["id"]], "foundational")
    assert r["id"] in alerts
    assert alerts[r["id"]] == "foundational"


async def test_supersede_alerts_tier_downgrade(team, data_path):
    """supersede_alerts fires when a lower tier supersedes a higher one."""
    from mulchd.domains import mulch_dir
    from mulchd.mcp.tier2 import supersede_alerts

    t = team
    r = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="tactical",
        content="Tactical rule",
        owner="carlos",
    )
    alerts = await supersede_alerts(mulch_dir("acme", "infra"), [r["id"]], "observational")
    assert r["id"] in alerts


async def test_supersede_alerts_no_alert_same_nonfoundational_tier(team, data_path):
    """supersede_alerts does not fire when tactical supersedes tactical."""
    from mulchd.domains import mulch_dir
    from mulchd.mcp.tier2 import supersede_alerts

    t = team
    r = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="tactical",
        content="Tactical rule",
        owner="carlos",
    )
    alerts = await supersede_alerts(mulch_dir("acme", "infra"), [r["id"]], "tactical")
    assert r["id"] not in alerts


def test_validate_references_accepts_existing_ids():
    from mulchd.mcp.tier2 import validate_references

    # Should not raise
    validate_references({"mx-a", "mx-b"}, ["mx-a"], ["mx-b"])


def test_validate_references_rejects_fabricated_supersedes_id():
    from mulchd.mcp.tier2 import validate_references

    with pytest.raises(ValueError, match="supersedes references records that don't exist: mx-ghost"):
        validate_references({"mx-a"}, ["mx-ghost"], [])


def test_validate_references_rejects_fabricated_relates_to_id():
    from mulchd.mcp.tier2 import validate_references

    with pytest.raises(ValueError, match="relates_to references records that don't exist: mx-ghost"):
        validate_references({"mx-a"}, [], ["mx-ghost"])


def test_validate_references_lists_multiple_bad_ids_in_one_error():
    from mulchd.mcp.tier2 import validate_references

    with pytest.raises(ValueError, match="mx-ghost1, mx-ghost2"):
        validate_references(set(), ["mx-ghost1", "mx-ghost2"], [])


def test_validate_references_rejects_self_reference():
    from mulchd.mcp.tier2 import validate_references

    with pytest.raises(ValueError, match="supersedes cannot reference the record's own id: mx-a"):
        validate_references({"mx-a"}, ["mx-a"], [], self_id="mx-a")


def test_validate_references_no_self_id_means_no_self_check():
    from mulchd.mcp.tier2 import validate_references

    # A brand-new write has no self_id yet (the record doesn't have an ID
    # until after write_record runs) — self_id=None must not raise just
    # because some coincidental ID appears in the live set.
    validate_references({"mx-a"}, ["mx-a"], [])


async def test_supersedes_foundational_annotated_on_superseder(team, data_path):
    """mark_superseded annotates _supersedes_foundational on the superseding record."""
    from mulchd.mcp.tier2 import mark_superseded

    t = team
    original = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="foundational",
        content="Guardrail",
        owner="carlos",
    )
    superseder = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="convention",
        classification="tactical",
        content="Weakened rule",
        owner="jorge",
        supersedes=[original["id"]],
    )
    original["_domain"] = "api"
    superseder["_domain"] = "api"

    records = [original, superseder]
    await mark_superseded(records, "acme", "infra")

    assert records[0].get("_superseded") is True
    assert records[1].get("_supersedes_foundational") == [original["id"]]


async def test_mark_superseded_tags_foundational_victim(team, data_path):
    """mark_superseded sets _foundational_superseded on a foundational record
    that has since been superseded — not on the superseder, and not on a
    foundational record that hasn't been superseded."""
    from mulchd.mcp.tier2 import mark_superseded

    t = team
    original = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="foundational", content="Guardrail", owner="carlos",
    )
    superseder = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="Weakened rule", owner="jorge",
        supersedes=[original["id"]],
    )
    untouched = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="foundational", content="Still standing", owner="carlos",
    )
    for r in (original, superseder, untouched):
        r["_domain"] = "api"

    records = [original, superseder, untouched]
    await mark_superseded(records, "acme", "infra")

    assert original.get("_foundational_superseded") is True
    assert superseder.get("_foundational_superseded") is None
    assert untouched.get("_foundational_superseded") is None


async def test_format_records_renders_foundational_superseded_banner(team, data_path):
    """format_records renders the loud banner instead of the plain line when
    _foundational_superseded is set, and keeps the plain line otherwise."""
    from mulchd.mcp.tier2 import format_records, mark_superseded

    t = team
    original = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="foundational", content="Guardrail", owner="carlos",
    )
    superseder = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="Weakened rule", owner="jorge",
        supersedes=[original["id"]],
    )
    tactical_old = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="Old tactical", owner="carlos",
    )
    tactical_new = _jot(
        data_path, "acme", "infra", "api",
        type="convention", classification="tactical", content="New tactical", owner="carlos",
        supersedes=[tactical_old["id"]],
    )
    for r in (original, superseder, tactical_old, tactical_new):
        r["_domain"] = "api"

    records = [original, tactical_old]
    await mark_superseded(records, "acme", "infra")
    text = format_records(records)

    assert f"FOUNDATIONAL POLICY SUPERSEDED by {superseder['id']}" in text
    assert f"get_record_history('{original['id']}')" in text
    assert f"superseded by {tactical_new['id']}" in text
    assert "FOUNDATIONAL POLICY SUPERSEDED" not in text.split(tactical_old["id"], 1)[1].split("\n")[0]


async def test_format_records_foundational_banner_includes_cross_domain_hint(team, data_path):
    """The foundational-superseded banner carries the same (in <domain>) suffix
    the plain 'superseded by' line shows — losing it would hide where the
    replacement actually lives, which defeats the banner's purpose."""
    from mulchd.mcp.tier2 import format_records, mark_superseded

    t = team
    original = _jot(
        data_path, "acme", "infra", "guardrails",
        type="convention", classification="foundational", content="Guardrail", owner="carlos",
    )
    superseder = _jot(
        data_path, "acme", "infra", "policies",
        type="convention", classification="foundational", content="Replacement", owner="jorge",
        supersedes=[original["id"]],
    )
    original["_domain"] = "guardrails"
    superseder["_domain"] = "policies"

    records = [original]
    await mark_superseded(records, "acme", "infra")
    text = format_records(records)

    assert f"FOUNDATIONAL POLICY SUPERSEDED by {superseder['id']} (in policies)" in text


async def test_mark_superseded_foundational_target_not_double_rendered(team, data_path):
    """A foundational supersede target must appear only in _supersedes_foundational,
    not also in the generic _supersedes_display — otherwise the id renders twice
    back-to-back in the formatted text (once per tag)."""
    from mulchd.mcp.tier2 import mark_superseded

    t = team
    old = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="foundational", content="Guardrail", owner="carlos",
    )
    new = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="Weakened rule", owner="carlos",
        supersedes=[old["id"]],
    )
    old["_domain"] = "infra"
    new["_domain"] = "infra"
    records = [old, new]
    await mark_superseded(records, "acme", "infra")

    assert new.get("_supersedes_display") in (None, [])
    assert new["_supersedes_foundational"] == [old["id"]]


async def test_mark_superseded_sets_generic_outgoing_tag(team, data_path):
    """A non-foundational outgoing supersedes relationship now gets a display
    tag too — today only the foundational-specific tag exists."""
    from mulchd.mcp.tier2 import mark_superseded

    t = team
    old = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="Old", owner="carlos",
    )
    new = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="New", owner="carlos",
        supersedes=[old["id"]],
    )
    old["_domain"] = "infra"
    new["_domain"] = "infra"
    records = [old, new]
    await mark_superseded(records, "acme", "infra")

    assert records[1]["_supersedes_display"] == [old["id"]]


async def test_mark_superseded_labels_deleted_target(team, data_path):
    """An outgoing supersedes target that's been archived is labeled (deleted),
    not shown as if it were still live."""
    from mulchd.domains import mulch_dir
    from mulchd.mcp.tier2 import mark_superseded

    t = team
    m_dir = mulch_dir("acme", "infra")
    archive_dir = m_dir / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "infra.jsonl").write_text(
        json.dumps({"id": "mx-archived1", "type": "convention", "classification": "tactical"}) + "\n"
    )
    new = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="New", owner="carlos",
        supersedes=["mx-archived1"],
    )
    new["_domain"] = "infra"
    records = [new]
    await mark_superseded(records, "acme", "infra")

    assert records[0]["_supersedes_display"] == ["mx-archived1 (deleted)"]


async def test_mark_superseded_labels_missing_target(team, data_path):
    """An outgoing supersedes target that never existed at all (legacy data
    written before write-time validation existed) is labeled (missing)."""
    from mulchd.mcp.tier2 import mark_superseded

    t = team
    new = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="New", owner="carlos",
        supersedes=["mx-never-existed"],
    )
    new["_domain"] = "infra"
    records = [new]
    await mark_superseded(records, "acme", "infra")

    assert records[0]["_supersedes_display"] == ["mx-never-existed (missing)"]


async def test_mark_superseded_flags_direct_cycle(team, data_path):
    """Two records that mutually supersede each other get _cycle_with set on both."""
    from mulchd.mcp.tier2 import mark_superseded

    t = team
    a = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="A", owner="carlos",
    )
    b = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="B", owner="carlos",
        supersedes=[a["id"]],
    )
    # Edit A directly in JSONL to also supersede B, completing the cycle
    path = data_path / "acme" / "infra" / ".mulch" / "expertise" / "infra.jsonl"
    lines = path.read_text().splitlines()
    new_lines = []
    for line in lines:
        rec = json.loads(line)
        if rec["id"] == a["id"]:
            rec["supersedes"] = [b["id"]]
        new_lines.append(json.dumps(rec))
    path.write_text("\n".join(new_lines) + "\n")

    a["_domain"] = "infra"
    b["_domain"] = "infra"
    records = [a, b]
    await mark_superseded(records, "acme", "infra")

    assert records[0].get("_cycle_with") == [b["id"]]
    assert records[1].get("_cycle_with") == [a["id"]]


def test_find_cycles_no_cycle_in_linear_chain():
    from mulchd.mcp.tier2 import _find_cycles

    records = [
        {"id": "mx-a", "supersedes": ["mx-b"]},
        {"id": "mx-b", "supersedes": ["mx-c"]},
        {"id": "mx-c", "supersedes": []},
    ]
    assert _find_cycles(records) == {}


def test_find_cycles_detects_direct_mutual_cycle():
    from mulchd.mcp.tier2 import _find_cycles

    records = [
        {"id": "mx-a", "supersedes": ["mx-b"]},
        {"id": "mx-b", "supersedes": ["mx-a"]},
    ]
    cycles = _find_cycles(records)
    assert set(cycles.keys()) == {"mx-a", "mx-b"}
    assert cycles["mx-a"] == ["mx-b"]
    assert cycles["mx-b"] == ["mx-a"]


def test_find_cycles_detects_transitive_three_node_cycle():
    from mulchd.mcp.tier2 import _find_cycles

    records = [
        {"id": "mx-a", "supersedes": ["mx-b"]},
        {"id": "mx-b", "supersedes": ["mx-c"]},
        {"id": "mx-c", "supersedes": ["mx-a"]},
    ]
    cycles = _find_cycles(records)
    assert set(cycles.keys()) == {"mx-a", "mx-b", "mx-c"}
    assert set(cycles["mx-a"]) == {"mx-b", "mx-c"}


def test_find_cycles_ignores_dangling_supersedes_target():
    """A supersedes reference to an ID not present among the given records
    (e.g. an already-archived target) can't participate in a cycle."""
    from mulchd.mcp.tier2 import _find_cycles

    records = [
        {"id": "mx-a", "supersedes": ["mx-ghost"]},
    ]
    assert _find_cycles(records) == {}


def test_find_cycles_unrelated_records_not_flagged():
    from mulchd.mcp.tier2 import _find_cycles

    records = [
        {"id": "mx-a", "supersedes": []},
        {"id": "mx-b", "supersedes": []},
    ]
    assert _find_cycles(records) == {}


def test_find_cycles_empty_input():
    from mulchd.mcp.tier2 import _find_cycles

    assert _find_cycles([]) == {}


def test_find_cycles_self_loop_not_flagged_as_cycle():
    """A record whose own supersedes list contains its own id (only reachable
    via legacy data written before validate_references existed) resolves to
    a single-node component and is correctly not treated as a cycle — a lone
    self-reference isn't a contradiction between two records the way A<->B is."""
    from mulchd.mcp.tier2 import _find_cycles

    records = [{"id": "mx-a", "supersedes": ["mx-a"]}]
    assert _find_cycles(records) == {}


def test_find_cycles_duplicate_ids_in_supersedes_list():
    """Duplicate IDs within one record's supersedes list must not corrupt the
    algorithm's bookkeeping (double-pushing onto the stack, duplicate entries
    in the reported cycle, etc.)."""
    from mulchd.mcp.tier2 import _find_cycles

    records = [
        {"id": "mx-a", "supersedes": ["mx-b", "mx-b"]},
        {"id": "mx-b", "supersedes": ["mx-a"]},
    ]
    cycles = _find_cycles(records)
    assert cycles["mx-a"] == ["mx-b"]
    assert cycles["mx-b"] == ["mx-a"]


def test_find_cycles_handles_long_chain_without_recursion_error():
    """A ~2000-record linear supersede chain must not crash — this is the
    scenario a recursive Tarjan's implementation fails on (Python's default
    recursion limit is 1000), and it's realistic: nothing prevents a
    long-lived project's supersede history from accumulating a chain this
    long over years of legitimate use."""
    from mulchd.mcp.tier2 import _find_cycles

    n = 2000
    records = [{"id": f"mx-{i}", "supersedes": [f"mx-{i + 1}"]} for i in range(n)]
    records.append({"id": f"mx-{n}", "supersedes": []})
    assert _find_cycles(records) == {}


async def test_read_records_marks_superseded(team, data_path):
    """When record B supersedes record A, A should be marked in text and structured output."""
    t = team
    old = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="Old approach",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="New approach",
        owner="carlos",
        supersedes=[old["id"]],
    )

    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra)
    )
    new_record = next(r for r in structured["records"] if r.get("supersedes"))
    assert "superseded" in text_content[0].text.lower()
    assert new_record["id"] in text_content[0].text  # superseded_by ID appears in text
    superseded_records = [r for r in structured["records"] if r.get("_superseded")]
    assert len(superseded_records) == 1
    assert superseded_records[0]["id"] == old["id"]
    assert superseded_records[0]["_superseded_by"] == new_record["id"]


async def test_non_superseded_records_not_marked(team, data_path):
    """Records not referenced in any supersedes list should not be marked."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="Standalone convention",
        owner="carlos",
    )

    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra)
    )
    assert "superseded" not in text_content[0].text
    assert not any(r.get("_superseded") for r in structured["records"])


async def test_superseded_marked_when_superseder_in_other_domain(team, data_path):
    """A record is marked superseded even when the superseding record lives in a different domain."""
    t = team
    old = _jot(
        data_path,
        "acme",
        "infra",
        "guardrails",
        type="convention",
        classification="foundational",
        content="Old guardrail",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "policies",
        type="convention",
        classification="foundational",
        content="Replacement rule",
        owner="carlos",
        supersedes=[old["id"]],
    )

    # Read only the victim's domain — superseder is not in the result set
    _, structured = await _read_expertise(
        {"domains": ["guardrails"]}, ctx(t.carlos, t.org, t.infra)
    )
    records = structured["records"]
    assert len(records) == 1
    assert records[0]["_superseded"] is True
    assert records[0]["_superseded_by"] is not None


async def test_superseded_marked_when_superseder_not_in_query_results(team, data_path):
    """Same-domain supersession: victim is marked even when the superseder didn't match the query."""
    t = team
    old = _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="Old approach",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="New approach",
        owner="jorge",
        supersedes=[old["id"]],
    )

    # Reading only carlos's records — superseder (jorge's) is filtered out
    _, structured = await _read_expertise({"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra))
    # Both records come back (no owner filter on read_records), but confirm
    # the old one is marked regardless of whether we'd have filtered the new one
    old_record = next(r for r in structured["records"] if r["id"] == old["id"])
    assert old_record["_superseded"] is True


async def test_read_records_renders_cycle_warning_not_normal_tags(team, data_path):
    """The formatted text output shows the CONTRADICTORY warning for a cycle,
    not the normal superseded/supersedes tags."""
    t = team
    a = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="A", owner="carlos",
    )
    b = _jot(
        data_path, "acme", "infra", "infra",
        type="convention", classification="tactical", content="B", owner="carlos",
        supersedes=[a["id"]],
    )
    path = data_path / "acme" / "infra" / ".mulch" / "expertise" / "infra.jsonl"
    lines = path.read_text().splitlines()
    new_lines = []
    for line in lines:
        rec = json.loads(line)
        if rec["id"] == a["id"]:
            rec["supersedes"] = [b["id"]]
        new_lines.append(json.dumps(rec))
    path.write_text("\n".join(new_lines) + "\n")

    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra)
    )
    assert "CONTRADICTORY" in text_content[0].text
    assert "superseded by" not in text_content[0].text
