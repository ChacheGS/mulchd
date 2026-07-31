"""Tests for the admin auth dependencies (require_admin, get_current_admin,
require_admin_json) and the AdminRequired exception + its redirect handler.

Each dependency is exercised through a tiny throwaway FastAPI app rather than
the real admin app, since what's under test is the dependency + exception
handler mechanism itself, not any particular route's business logic.
"""

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from mulchd.admin._shared import (
    AdminRequired,
    get_current_admin,
    redirect_login,
    require_admin,
    require_admin_json,
)


def _test_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(AdminRequired)
    async def _handler(request, exc):
        return redirect_login()

    @app.get("/needs-admin", dependencies=[Depends(require_admin)])
    async def needs_admin():
        return {"ok": True}

    @app.get("/needs-admin-user")
    async def needs_admin_user(admin=Depends(get_current_admin)):
        return {"username": admin.username}

    @app.get("/needs-admin-json", dependencies=[Depends(require_admin_json)])
    async def needs_admin_json():
        return {"ok": True}

    return app


async def test_require_admin_redirects_unauthenticated(db):
    app = _test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/needs-admin", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/connect"


async def test_require_admin_redirects_authenticated_non_admin(db):
    from mulchd.auth import create_user
    from mulchd.connect import _signer

    user, _ = await create_user("regular", "Regular User")
    app = _test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac.cookies.set("mulchd_connect", _signer().dumps(user.id))
        resp = await ac.get("/needs-admin", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/connect"


async def test_require_admin_allows_superadmin(db):
    from mulchd.admin_grants import grant_superadmin
    from mulchd.auth import create_user
    from mulchd.connect import _signer

    user, _ = await create_user("admin", "Admin")
    await grant_superadmin(user, granted_by=user)
    app = _test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac.cookies.set("mulchd_connect", _signer().dumps(user.id))
        resp = await ac.get("/needs-admin", follow_redirects=False)
    assert resp.status_code == 200


async def test_get_current_admin_returns_the_user(db):
    from mulchd.admin_grants import grant_superadmin
    from mulchd.auth import create_user
    from mulchd.connect import _signer

    user, _ = await create_user("admin2", "Admin Two")
    await grant_superadmin(user, granted_by=user)
    app = _test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac.cookies.set("mulchd_connect", _signer().dumps(user.id))
        resp = await ac.get("/needs-admin-user", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin2"


async def test_get_current_admin_redirects_when_not_admin(db):
    app = _test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/needs-admin-user", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/connect"


async def test_require_admin_json_returns_403_unauthenticated(db):
    app = _test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/needs-admin-json")
    assert resp.status_code == 403
