"""
get_recent timestamp-filtering tests.
"""

from datetime import datetime, timedelta, timezone
from mulchd.mcp.tier2 import _get_recent
from tests.mcp.conftest import ctx, _jot


async def test_get_recent_excludes_old_records(team, data_path):
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

    result = await _get_recent(
        {"since": cutoff.isoformat(), "domains": ["infra"]},
        ctx(t.jorge, t.org, t.infra),
    )
    text = result[0].text
    assert "New decision post-migration" in text
    assert "Old practice" not in text


async def test_get_recent_multiple_domains(team, data_path):
    """get_recent aggregates across domains when multiple are specified."""
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

    result = await _get_recent(
        {"since": since.isoformat(), "domains": ["infra", "governance"]},
        ctx(t.carlos, t.org, t.infra),
    )
    text = result[0].text
    assert "Infra domain record" in text
    assert "Governance domain record" in text
