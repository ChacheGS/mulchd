"""
Transitive supersede-chain resolution: _resolve_tips, and the tip annotations
_mark_superseded adds for chains deeper than one hop.
"""

from mulchd.mcp.formatting import _decorate_header
from mulchd.mcp.supersession import _mark_superseded, _resolve_tips
from tests.mcp.conftest import _jot


def test_header_replaces_immediate_superseder_with_the_tip():
    """An unambiguous tip stands in for the hop, which is stale by definition."""
    header = _decorate_header(
        "mx-a",
        {
            "id": "mx-a",
            "_superseded": True,
            "_superseded_by": "mx-b",
            "_superseded_tip": "mx-c",
            "_superseded_tip_hops": 2,
        },
    )
    assert "superseded by mx-c (current tip, 2 hops)" in header
    assert "mx-b" not in header


def test_header_keeps_single_hop_render_unchanged():
    header = _decorate_header(
        "mx-a",
        {"id": "mx-a", "_superseded": True, "_superseded_by": "mx-b"},
    )
    assert header == "mx-a • superseded by mx-b"


def test_header_shows_tip_domain_when_it_differs():
    header = _decorate_header(
        "mx-a",
        {
            "id": "mx-a",
            "_superseded": True,
            "_superseded_by": "mx-b",
            "_superseded_tip": "mx-c",
            "_superseded_tip_hops": 2,
            "_superseded_tip_domain": "ops",
        },
    )
    assert "superseded by mx-c (in ops) (current tip, 2 hops)" in header


def test_header_flags_ambiguous_tips_and_keeps_the_hop():
    """With no single tip there is nothing to replace the hop with, so it stays."""
    header = _decorate_header(
        "mx-a",
        {
            "id": "mx-a",
            "_superseded": True,
            "_superseded_by": "mx-b",
            "_superseded_tip_ambiguous": ["mx-c", "mx-d"],
        },
    )
    assert "superseded by mx-b" in header
    assert "current tip ambiguous (2 branches): mx-c, mx-d" in header


def test_header_appends_tip_to_foundational_banner():
    """The foundational alert keeps naming its direct replacement and adds the tip."""
    header = _decorate_header(
        "mx-a",
        {
            "id": "mx-a",
            "_superseded": True,
            "_foundational_superseded": True,
            "_superseded_by": "mx-b",
            "_superseded_tip": "mx-c",
            "_superseded_tip_hops": 2,
        },
    )
    assert "FOUNDATIONAL POLICY SUPERSEDED by mx-b" in header
    assert "current tip: mx-c (2 hops)" in header


def test_resolve_tips_single_hop_returns_immediate_superseder():
    superseders = {"mx-a": ["mx-b"]}
    assert _resolve_tips("mx-a", superseders, {}) == (["mx-b"], 1)


def test_resolve_tips_walks_two_hop_chain_to_the_end():
    superseders = {"mx-a": ["mx-b"], "mx-b": ["mx-c"]}
    assert _resolve_tips("mx-a", superseders, {}) == (["mx-c"], 2)


def test_resolve_tips_walks_long_chain():
    superseders = {f"mx-{i}": [f"mx-{i + 1}"] for i in range(50)}
    assert _resolve_tips("mx-0", superseders, {}) == (["mx-50"], 50)


def test_resolve_tips_returns_every_tip_of_a_fork():
    superseders = {"mx-a": ["mx-b", "mx-c"]}
    tips, _ = _resolve_tips("mx-a", superseders, {})
    assert tips == ["mx-b", "mx-c"]


def test_resolve_tips_returns_every_tip_of_a_deep_fork():
    superseders = {"mx-a": ["mx-b"], "mx-b": ["mx-c", "mx-d"], "mx-d": ["mx-e"]}
    tips, _ = _resolve_tips("mx-a", superseders, {})
    assert tips == ["mx-c", "mx-e"]


def test_resolve_tips_collapses_diamond_to_one_tip():
    """Two branches reconverging on the same record leave a single tip, not two."""
    superseders = {"mx-a": ["mx-b", "mx-c"], "mx-b": ["mx-d"], "mx-c": ["mx-d"]}
    tips, _ = _resolve_tips("mx-a", superseders, {})
    assert tips == ["mx-d"]


def test_resolve_tips_stops_before_cycle_members():
    """A chain running into a cycle resolves to the last acyclic record."""
    superseders = {"mx-a": ["mx-b"], "mx-b": ["mx-c"], "mx-c": ["mx-b"]}
    cycles = {"mx-b": ["mx-c"], "mx-c": ["mx-b"]}
    assert _resolve_tips("mx-a", superseders, cycles) == ([], 0)


def test_resolve_tips_terminates_when_the_record_itself_is_in_a_cycle():
    superseders = {"mx-a": ["mx-b"], "mx-b": ["mx-a"]}
    cycles = {"mx-a": ["mx-b"], "mx-b": ["mx-a"]}
    assert _resolve_tips("mx-a", superseders, cycles) == ([], 0)


def test_resolve_tips_unsuperseded_record_has_no_tip():
    assert _resolve_tips("mx-a", {}, {}) == ([], 0)


async def test_mark_superseded_annotates_tip_on_two_hop_chain(team, data_path):
    """Reading the oldest record of A<-B<-C surfaces C, not just B."""
    a = _jot(data_path, "acme", "infra", "api", type="decision", content="First", owner="carlos")
    b = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="decision",
        content="Second",
        owner="carlos",
        supersedes=[a["id"]],
    )
    c = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="decision",
        content="Third",
        owner="carlos",
        supersedes=[b["id"]],
    )
    a["_domain"] = "api"
    records = [a]
    await _mark_superseded(records, "acme", "infra")

    assert a["_superseded_by"] == b["id"]
    assert a["_superseded_tip"] == c["id"]
    assert a["_superseded_tip_hops"] == 2
    assert not a.get("_superseded_tip_ambiguous")


async def test_mark_superseded_omits_tip_when_superseder_is_current(team, data_path):
    """A one-hop supersession gets no tip annotation, so its render is unchanged."""
    a = _jot(data_path, "acme", "infra", "api", type="decision", content="First", owner="carlos")
    _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="decision",
        content="Second",
        owner="carlos",
        supersedes=[a["id"]],
    )
    a["_domain"] = "api"
    records = [a]
    await _mark_superseded(records, "acme", "infra")

    assert a.get("_superseded_tip") is None
    assert a.get("_superseded_tip_hops") is None


async def test_mark_superseded_flags_ambiguous_tips_on_a_fork(team, data_path):
    """Two live records superseding the same victim resolve to no single tip."""
    a = _jot(data_path, "acme", "infra", "api", type="decision", content="First", owner="carlos")
    b = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="decision",
        content="Branch one",
        owner="carlos",
        supersedes=[a["id"]],
    )
    c = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="decision",
        content="Branch two",
        owner="jorge",
        supersedes=[a["id"]],
    )
    a["_domain"] = "api"
    records = [a]
    await _mark_superseded(records, "acme", "infra")

    assert a["_superseded_tip_ambiguous"] == sorted([b["id"], c["id"]])
    assert a.get("_superseded_tip") is None


async def test_mark_superseded_records_tip_domain_for_cross_domain_chain(team, data_path):
    """The tip's domain is reported, not the intermediate superseder's."""
    a = _jot(data_path, "acme", "infra", "api", type="decision", content="First", owner="carlos")
    b = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="decision",
        content="Second",
        owner="carlos",
        supersedes=[a["id"]],
    )
    c = _jot(
        data_path,
        "acme",
        "infra",
        "ops",
        type="decision",
        content="Third",
        owner="carlos",
        supersedes=[b["id"]],
    )
    a["_domain"] = "api"
    records = [a]
    await _mark_superseded(records, "acme", "infra")

    assert a["_superseded_tip"] == c["id"]
    assert a["_superseded_tip_domain"] == "ops"


async def test_format_records_surfaces_the_tip_for_a_mid_chain_record(team, data_path):
    """Reading B of A<-B<-C names C, so no second fetch is needed to learn B is stale."""
    from mulchd.mcp.tier2 import _format_records

    a = _jot(data_path, "acme", "infra", "api", type="decision", content="First", owner="carlos")
    b = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="decision",
        content="Second",
        owner="carlos",
        supersedes=[a["id"]],
    )
    c = _jot(
        data_path,
        "acme",
        "infra",
        "api",
        type="decision",
        content="Third",
        owner="carlos",
        supersedes=[b["id"]],
    )
    for r in (a, b, c):
        r["_domain"] = "api"

    records = [a, b]
    await _mark_superseded(records, "acme", "infra")
    text = _format_records(records)

    assert f"superseded by {c['id']} (current tip, 2 hops)" in text
    assert f"superseded by {c['id']}" in text.split(b["id"], 1)[1]


async def test_mark_superseded_leaves_cycle_members_untagged(team, data_path):
    """A chain into a cycle still yields no tip and no supersede tag on the cycle."""
    a = _jot(data_path, "acme", "infra", "api", type="decision", content="First", owner="carlos")
    b = _jot(data_path, "acme", "infra", "api", type="decision", content="Second", owner="carlos")
    c = _jot(data_path, "acme", "infra", "api", type="decision", content="Third", owner="carlos")

    path = data_path / "acme" / "infra" / ".mulch" / "expertise" / "api.jsonl"
    import json

    lines = []
    for line in path.read_text().splitlines():
        r = json.loads(line)
        if r["id"] == b["id"]:
            r["supersedes"] = [a["id"], c["id"]]
        elif r["id"] == c["id"]:
            r["supersedes"] = [b["id"]]
        lines.append(json.dumps(r))
    path.write_text("\n".join(lines) + "\n")

    a["_domain"] = "api"
    records = [a]
    await _mark_superseded(records, "acme", "infra")

    assert a.get("_superseded_tip") is None
    assert a.get("_superseded_tip_ambiguous") is None
