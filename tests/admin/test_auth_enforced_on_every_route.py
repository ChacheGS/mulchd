"""
Enumerates every route registered on the admin router and asserts each one
enforces auth via the expected mechanism — a 303 redirect for HTML admin
pages, a 403 for the one JSON API route. Per-route "requires auth" tests
exist for some pages but not all — this test is the safety net that catches
a forgotten (or regressed) check on any route, including ones added later,
without anyone having to remember to write a dedicated test for it.
"""

import pytest

from mulchd.admin import router as admin_router

_PATH_PARAM_PLACEHOLDERS = {
    "org": "acme",
    "project": "infra",
    "user_id": "1",
    "project_id": "1",
    "membership_id": "1",
    "token_id": "1",
    "invite_id": "1",
    "identity_id": "1",
}

_JSON_403_PATHS = {"/admin/api/usage/acme/infra"}


def _discover_routes() -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for sub in admin_router.routes:
        original = getattr(sub, "original_router", None)
        targets = original.routes if original is not None else [sub]
        for r in targets:
            methods = sorted(m for m in (r.methods or []) if m != "HEAD")
            path = "/admin" + r.path
            for name, value in _PATH_PARAM_PLACEHOLDERS.items():
                path = path.replace(f"{{{name}}}", value)
            for method in methods:
                routes.append((method, path))
    return routes


_ROUTES = _discover_routes()


def _expected_status(path: str) -> int:
    return 403 if path in _JSON_403_PATHS else 303


@pytest.mark.parametrize("method,path", _ROUTES, ids=[f"{m} {p}" for m, p in _ROUTES])
async def test_route_rejects_unauthenticated_request(client, method, path):
    resp = await client.request(method, path, follow_redirects=False)
    expected = _expected_status(path)
    assert resp.status_code == expected, (
        f"{method} {path} returned {resp.status_code} for an unauthenticated request, "
        f"expected {expected}"
    )
    if expected == 303:
        assert resp.headers["location"] == "/connect"


@pytest.mark.parametrize("method,path", _ROUTES, ids=[f"{m} {p}" for m, p in _ROUTES])
async def test_route_rejects_authenticated_non_admin_request(client, method, path):
    from mulchd.auth import create_user
    from mulchd.connect import _signer

    user, _ = await create_user(f"nonadmin-{abs(hash((method, path)))}", "Non Admin")
    client.cookies.set("mulchd_connect", _signer().dumps(user.id))

    resp = await client.request(method, path, follow_redirects=False)
    expected = _expected_status(path)
    assert resp.status_code == expected, (
        f"{method} {path} returned {resp.status_code} for an authenticated non-admin request, "
        f"expected {expected}"
    )
    if expected == 303:
        assert resp.headers["location"] == "/connect"


def test_discovered_at_least_the_known_route_count():
    """Guards against the discovery walk itself silently finding nothing —
    a bug there would make every parametrized case above vacuously trivial."""
    assert len(_ROUTES) >= 33
