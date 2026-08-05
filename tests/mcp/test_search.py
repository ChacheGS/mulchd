"""
search_records — per-domain result limit.

mulch's own BM25(+confirmation-boost) ranking is genuine and already applied
within each domain by the time results reach mulchd (confirmed by reading
mulch's source: search.ts / bm25.ts / scoring.ts) — mulch just doesn't expose
the numeric score or merge multiple domains into one global rank. So capping
each domain's matches to the first `limit` is a real relevance cutoff, not an
arbitrary one; it is NOT a global top-N across domains, since there's no
cross-domain score to rank by.
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


async def test_search_records_names_org_project(team, data_path, monkeypatch):
    """Names the org/project so an agent juggling multiple mulchd connections
    can catch a search against the wrong target."""
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _search_expertise

    t = team
    monkeypatch.setattr(mcp_tier2, "search_domains", _fake_search_domains({"infra": 1}))

    text_content, _ = await _search_expertise({"query": "x"}, ctx(t.carlos, t.org, t.infra))

    assert "acme/infra" in text_content[0].text


async def test_search_caps_each_domain_to_the_default_limit(team, data_path, monkeypatch):
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _search_expertise

    t = team
    monkeypatch.setattr(mcp_tier2, "search_domains", _fake_search_domains({"infra": 25, "ops": 5}))

    _, structured = await _search_expertise({"query": "x"}, ctx(t.carlos, t.org, t.infra))

    by_domain: dict[str, int] = {}
    for r in structured["records"]:
        by_domain[r["_domain"]] = by_domain.get(r["_domain"], 0) + 1
    assert by_domain == {"infra": 20, "ops": 5}
    assert structured["truncated"] is True


async def test_search_respects_explicit_limit(team, data_path, monkeypatch):
    import mulchd.mcp.tier2 as mcp_tier2
    from mulchd.mcp.tier2 import _search_expertise

    t = team
    monkeypatch.setattr(mcp_tier2, "search_domains", _fake_search_domains({"infra": 10}))

    _, structured = await _search_expertise({"query": "x", "limit": 3}, ctx(t.carlos, t.org, t.infra))

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

    _, structured = await _search_expertise({"query": "x", "limit": 2}, ctx(t.carlos, t.org, t.infra))

    ids = [r["id"] for r in structured["records"]]
    assert ids == ["mx-infra-0", "mx-infra-1"]
