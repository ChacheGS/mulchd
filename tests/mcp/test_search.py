"""
search_records — round-robin global result limit.

mulch's own BM25(+confirmation-boost) ranking is genuine and already applied
within each domain by the time results reach mulchd (confirmed by reading
mulch's source: search.ts / bm25.ts / scoring.ts) — mulch just doesn't expose
the numeric score or merge multiple domains into one global rank. Since
cross-domain BM25 scores aren't comparable, `limit` is enforced as a global
total by round-robining across domains (taking turns, not ranking across
them) while preserving each domain's own relevance order untouched.
"""

from tests.mcp.conftest import ctx


def _fake_record(domain: str, n: int) -> dict:
    return {
        "id": f"mx-{domain}-{n}",
        "type": "convention",
        "classification": "tactical",
        "owner": "carlos",
        "recorded_at": "2026-07-01T00:00:00+00:00",
        "content": f"{domain} match {n}",
        "_domain": domain,
    }


def _fake_search_domains(records_by_domain: dict[str, int]):
    async def _fake(m_dir, query, domains):
        return [
            _fake_record(domain, i)
            for domain, count in records_by_domain.items()
            for i in range(count)
        ]

    return _fake


def test_search_records_schema_does_not_describe_stale_per_domain_semantics():
    """The tool contract (description + limit param) must match the
    round-robin, global-total implementation — not the old per-domain-cap
    behavior it replaced. A client trusting the advertised schema over the
    source should not be misled."""
    from mulchd.mcp.schemas import TIER2_TOOLS

    search_tool = next(t for t in TIER2_TOOLS if t.name == "search_records")
    description = search_tool.description or ""
    limit_description = search_tool.input_schema["properties"]["limit"]["description"]

    for stale_text in ("per matching domain", "not a global total"):
        assert stale_text not in description.lower()
        assert stale_text not in limit_description.lower()


async def test_search_records_names_org_project(team, data_path, monkeypatch):
    """Names the org/project so an agent juggling multiple mulchd connections
    can catch a search against the wrong target."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _search_expertise

    t = team
    monkeypatch.setattr(mcp_tier2, "search_domains", _fake_search_domains({"infra": 1}))

    text_content, _ = await _search_expertise({"query": "x"}, ctx(t.carlos, t.org, t.infra))

    assert "acme/infra" in text_content[0].text


async def test_search_round_robins_across_domains_up_to_the_default_limit(
    team, data_path, monkeypatch
):
    """default_page_size (not a hardcoded 20) is search's default, and it's a
    global total distributed round-robin across matching domains, not a
    per-domain cap."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _search_expertise

    t = team
    monkeypatch.setattr(mcp_tier2, "search_domains", _fake_search_domains({"infra": 25, "ops": 5}))

    _, structured = await _search_expertise({"query": "x"}, ctx(t.carlos, t.org, t.infra))

    assert len(structured["records"]) == 30  # 25 + 5, under the default_page_size=50 cap
    assert structured["truncated"] is False


async def test_search_round_robin_order_when_a_domain_exhausts_early(team, data_path, monkeypatch):
    """One domain running out of matches mid-cycle must not shortchange the
    total — its leftover slots go to domains that still have matches."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _search_expertise

    t = team
    monkeypatch.setattr(mcp_tier2, "search_domains", _fake_search_domains({"infra": 25, "ops": 2}))

    _, structured = await _search_expertise(
        {"query": "x", "limit": 6}, ctx(t.carlos, t.org, t.infra)
    )

    ids = [r["id"] for r in structured["records"]]
    assert ids == [
        "mx-infra-0", "mx-ops-0",
        "mx-infra-1", "mx-ops-1",
        "mx-infra-2", "mx-infra-3",
    ]
    assert structured["truncated"] is True


async def test_search_respects_explicit_limit(team, data_path, monkeypatch):
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _search_expertise

    t = team
    monkeypatch.setattr(mcp_tier2, "search_domains", _fake_search_domains({"infra": 10}))

    _, structured = await _search_expertise(
        {"query": "x", "limit": 3}, ctx(t.carlos, t.org, t.infra)
    )

    assert len(structured["records"]) == 3
    assert structured["truncated"] is True


async def test_search_not_truncated_when_under_limit(team, data_path, monkeypatch):
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _search_expertise

    t = team
    monkeypatch.setattr(mcp_tier2, "search_domains", _fake_search_domains({"infra": 3, "ops": 2}))

    _, structured = await _search_expertise({"query": "x"}, ctx(t.carlos, t.org, t.infra))

    assert len(structured["records"]) == 5
    assert structured["truncated"] is False


async def test_search_preserves_relevance_order_within_the_cap(team, data_path, monkeypatch):
    """mulch already returns each domain's matches in BM25(+boost) rank order —
    capping must keep the first N, not resort or reorder them."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _search_expertise

    t = team
    monkeypatch.setattr(mcp_tier2, "search_domains", _fake_search_domains({"infra": 5}))

    _, structured = await _search_expertise(
        {"query": "x", "limit": 2}, ctx(t.carlos, t.org, t.infra)
    )

    ids = [r["id"] for r in structured["records"]]
    assert ids == ["mx-infra-0", "mx-infra-1"]
