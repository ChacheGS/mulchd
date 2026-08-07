import pytest


async def test_root_requires_auth(client):
    resp = await client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_root_rejects_non_admin_user(client):
    from mulchd.auth import create_user
    from mulchd.connect import _signer

    user, _ = await create_user("regular", "Regular User")
    signed = _signer().dumps(user.id)
    client.cookies.set("mulchd_connect", signed)
    resp = await client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_root_redirects_to_activity(admin_client):
    resp = await admin_client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin/activity"
