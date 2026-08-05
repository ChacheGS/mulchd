"""
list_domains tests.
"""

from mulchd.mcp.tier2 import _list_domains, _record_expertise
from tests.mcp.conftest import _jot, ctx


async def test_list_domains_isolation_different_projects(team, data_path):
    """list_domains record counts are per-project, not shared."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="r1",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="decision",
        classification="foundational",
        content="r2",
        owner="jorge",
    )

    # infra project: 2 records in the infra domain
    text_content, structured = await _list_domains(ctx(t.carlos, t.org, t.infra), "2025-11-25")
    assert "2 records" in text_content[0].text

    # data-platform project: no expertise files at all → no domains listed
    text_content, structured = await _list_domains(ctx(t.jorge, t.org, t.data), "2025-11-25")
    assert "infra" not in text_content[0].text


async def test_list_domains_shows_org_and_project_name(team, data_path):
    t = team
    text_content, structured = await _list_domains(ctx(t.carlos, t.org, t.infra), "2025-11-25")
    assert "Acme Corp" in text_content[0].text
    assert "Infrastructure" in text_content[0].text


async def test_list_domains_counts_match_written_records(team, data_path):
    t = team
    for _ in range(3):
        _jot(
            data_path,
            "acme",
            "infra",
            "infra",
            type="convention",
            classification="observational",
            content="record",
            owner="carlos",
        )

    text_content, structured = await _list_domains(ctx(t.carlos, t.org, t.infra), "2025-11-25")
    assert "3 records" in text_content[0].text


async def test_list_domains_structured_includes_recent_hint(team, data_path):
    """list_domains structured output should carry the recent-activity hint so clients
    consuming structured content don't lose the session-start instruction."""
    t = team
    _, structured = await _list_domains(ctx(t.carlos, t.org, t.infra), "2025-11-25")
    assert (
        "recent_hint" in structured or "hint" in structured
    ), "structured output must include the read_records(since=...) hint"


async def test_list_domains_structured_includes_domain_uri(team, data_path, fake_write_record):
    """Each domain entry should carry its resource URI so agents don't have to
    hand-construct mulchd://<org>/<project>/domain/<name> or make a separate
    list_resources call."""
    t = team
    await _record_expertise(
        {
            "domain": "infra",
            "type": "convention",
            "classification": "tactical",
            "content": "Use IMDSv2 on all EC2 instances",
        },
        ctx(t.carlos, t.org, t.infra),
    )

    _, structured = await _list_domains(ctx(t.carlos, t.org, t.infra), "2025-11-25")
    assert structured["domains"], "expected at least one domain after writing a record"
    for d in structured["domains"]:
        assert d["uri"] == f"mulchd://{t.org.slug}/{t.infra.slug}/domain/{d['name']}"


async def test_list_domains_reports_negotiated_protocol_version(team, data_path):
    """The agent has no other way to tell which subscription mechanism the
    SESSION_WORKFLOW instructions expect it to use — list_domains must surface
    the version the server actually negotiated with this connection."""
    t = team
    text_content, structured = await _list_domains(ctx(t.carlos, t.org, t.infra), "2026-07-28")
    assert "2026-07-28" in text_content[0].text
    assert structured["protocol_version"] == "2026-07-28"


async def test_list_domains_structured_includes_language(team, data_path):
    """list_domains structured output should expose knowledge_language when set,
    so clients using structured content still receive the translation directive."""
    t = team
    t.infra.knowledge_language = "es"
    await t.infra.save()

    _, structured = await _list_domains(ctx(t.carlos, t.org, t.infra), "2025-11-25")
    assert structured.get("language") == "es"
