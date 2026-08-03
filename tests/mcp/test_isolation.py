"""
Cross-project / cross-user isolation tests.
"""

from datetime import datetime, timedelta, timezone
from mulchd.mcp.tier2 import _read_expertise
from tests.mcp.conftest import ctx, _jot


async def test_read_isolation_different_projects(team, data_path):
    """Records written to infra are invisible when reading from data-platform."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="decision",
        classification="foundational",
        content="Use Terraform for all infra",
        owner="carlos",
    )

    # Member of both projects reading from infra sees the record.
    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.jorge, t.org, t.infra)
    )
    assert "Terraform" in text_content[0].text

    # Same user reading from data-platform sees nothing.
    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.jorge, t.org, t.data)
    )
    assert "Terraform" not in text_content[0].text
    assert "No records found" in text_content[0].text


async def test_read_records_since_isolation_different_projects(team, data_path):
    """read_records(since=...) respects project boundaries even when both
    projects share an org."""
    t = team
    since = datetime.now(timezone.utc) - timedelta(seconds=1)

    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="foundational",
        content="VPCs use /16 CIDR blocks",
        owner="carlos",
    )

    text_content, structured = await _read_expertise(
        {"since": since.isoformat(), "domains": ["infra"]},
        ctx(t.jorge, t.org, t.infra),
    )
    assert "VPCs use /16 CIDR blocks" in text_content[0].text

    text_content, structured = await _read_expertise(
        {"since": since.isoformat(), "domains": ["infra"]},
        ctx(t.jorge, t.org, t.data),
    )
    assert "VPCs use /16 CIDR blocks" not in text_content[0].text
    assert "No records" in text_content[0].text


async def test_cross_user_read_sees_all_project_records(team, data_path):
    """All project members see records regardless of who wrote them."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="failure",
        classification="foundational",
        content="NAT gateway quota exhaustion caused prod outage",
        owner="carlos",
    )

    # jorge reads and sees carlos's record with author attribution
    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.jorge, t.org, t.infra)
    )
    assert "NAT gateway quota exhaustion" in text_content[0].text
    assert "carlos" in text_content[0].text


async def test_multiple_authors_all_visible_to_team(team, data_path):
    """Records from multiple authors are all visible to every project member."""
    t = team
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="decision",
        classification="foundational",
        content="Prefer Aurora Serverless for managed DBs",
        owner="carlos",
    )
    _jot(
        data_path,
        "acme",
        "infra",
        "infra",
        type="convention",
        classification="tactical",
        content="Tag all resources with team and cost-centre",
        owner="jorge",
    )

    # ana is not in infra, but carlos is — carlos sees both records
    text_content, structured = await _read_expertise(
        {"domains": ["infra"]}, ctx(t.carlos, t.org, t.infra)
    )
    text = text_content[0].text
    assert "Aurora Serverless" in text
    assert "Tag all resources" in text
    assert "carlos" in text
    assert "jorge" in text
