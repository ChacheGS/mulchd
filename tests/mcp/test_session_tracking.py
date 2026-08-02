"""_get_or_create_session — in-memory (user, project) session tracking."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import mulchd.mcp.tier2 as tier2


def test_get_or_create_session_reuses_live_entry(monkeypatch):
    monkeypatch.setattr(tier2, "_active_sessions", {})
    sid1 = tier2._get_or_create_session(1, 1)
    sid2 = tier2._get_or_create_session(1, 1)
    assert sid1 == sid2


def test_get_or_create_session_evicts_expired_entries(monkeypatch):
    """A (user, project) pair that goes idle past the session window must not
    linger in the dict forever — it should be swept on the next call, even one
    for an unrelated key."""
    monkeypatch.setattr(tier2, "_active_sessions", {})
    expired_key = (99, 99)
    tier2._active_sessions[expired_key] = (
        uuid4(),
        datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    tier2._get_or_create_session(1, 1)

    assert expired_key not in tier2._active_sessions
