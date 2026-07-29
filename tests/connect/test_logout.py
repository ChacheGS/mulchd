import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

from tests.connect.conftest import _authed_client

# ── logout ───────────────────────────────────────────────────────────────────


async def test_connect_logout_clears_cookie(client, alice_and_project):
    user, token, *_ = alice_and_project
    await _authed_client(client, token)
    resp = await client.get("/connect/logout", follow_redirects=False)
    assert resp.status_code == 303
    # Cookie should be cleared (max_age=0 or deleted)
    assert "mulchd_connect" not in client.cookies or client.cookies["mulchd_connect"] == ""
