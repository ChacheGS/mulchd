"""
App startup validates policy env vars.
"""

import pytest


async def test_lifespan_raises_on_malformed_policy_env_var(monkeypatch):
    monkeypatch.setenv("MULCHD_POLICY_DEFAULT_PAGE_SIZE", "notanumber")
    from mulchd.main import lifespan

    with pytest.raises(ValueError, match="MULCHD_POLICY_DEFAULT_PAGE_SIZE"):
        async with lifespan(None):
            pass
