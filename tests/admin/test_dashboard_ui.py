import pytest


async def test_dashboard_requires_auth(client):
    resp = await client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_dashboard_rejects_non_admin_user(client):
    from mulchd.auth import create_user
    from mulchd.connect import _signer

    user, _ = await create_user("regular", "Regular User")
    signed = _signer().dumps(user.id)
    client.cookies.set("mulchd_connect", signed)
    resp = await client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_dashboard_renders(admin_client):
    resp = await admin_client.get("/admin/")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text
    assert 'id="usage-chart"' not in resp.text
    assert "loadUsageChart" not in resp.text
