"""
write_* tools warn (non-blocking) when writing to a new domain whose name is
a near-duplicate of an existing one — catches typos like "architecutre" vs
"architecture" before they silently fragment the knowledge base.
"""

from mulchd.mcp.tier2 import _record_expertise
from tests.mcp.conftest import ctx, _jot


async def test_write_warns_on_near_duplicate_domain_name(team, data_path, fake_write_record):
    t = team
    _jot(
        data_path, "acme", "infra", "architecture",
        type="convention", classification="tactical", content="existing", owner="carlos",
    )

    result = await _record_expertise(
        {
            "domain": "architecutre",
            "type": "convention",
            "classification": "tactical",
            "content": "typo'd domain",
        },
        ctx(t.carlos, t.org, t.infra),
    )

    text = result[0].text
    assert "did you mean the existing domain 'architecture'" in text
    # non-blocking — the write still succeeds in the typo'd domain
    assert "architecutre" in text


async def test_write_no_warning_for_genuinely_new_domain(team, data_path, fake_write_record):
    t = team
    _jot(
        data_path, "acme", "infra", "architecture",
        type="convention", classification="tactical", content="existing", owner="carlos",
    )

    result = await _record_expertise(
        {
            "domain": "kubernetes",
            "type": "convention",
            "classification": "tactical",
            "content": "unrelated new domain",
        },
        ctx(t.carlos, t.org, t.infra),
    )

    assert "did you mean" not in result[0].text


async def test_write_no_warning_when_domain_already_exists(team, data_path, fake_write_record):
    """Writing to an existing domain is never a 'new domain' — no near-dup
    check should even run, regardless of how similar its name is to others."""
    t = team
    _jot(
        data_path, "acme", "infra", "architecture",
        type="convention", classification="tactical", content="existing", owner="carlos",
    )

    result = await _record_expertise(
        {
            "domain": "architecture",
            "type": "convention",
            "classification": "tactical",
            "content": "another record in the same domain",
        },
        ctx(t.carlos, t.org, t.infra),
    )

    assert "did you mean" not in result[0].text


async def test_write_no_warning_for_first_domain_in_project(team, data_path, fake_write_record):
    """No existing domains at all — nothing to compare against, no crash."""
    t = team

    result = await _record_expertise(
        {
            "domain": "infra",
            "type": "convention",
            "classification": "tactical",
            "content": "first record ever",
        },
        ctx(t.carlos, t.org, t.infra),
    )

    assert "did you mean" not in result[0].text
