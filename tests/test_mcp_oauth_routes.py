import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


async def test_well_known_authorization_server_present(client, db):
    resp = await client.get("/.well-known/oauth-authorization-server")
    assert resp.status_code == 200
    body = resp.json()
    assert body["registration_endpoint"].endswith("/register")
    assert body["authorization_endpoint"].endswith("/authorize")
    assert body["token_endpoint"].endswith("/token")


async def test_well_known_protected_resource_present(client, db):
    resp = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resource"].endswith("/mcp")


async def test_register_endpoint_creates_client(client, db):
    resp = await client.post(
        "/register",
        json={
            "redirect_uris": ["http://localhost:1234/cb"],
            "token_endpoint_auth_method": "none",
            "client_name": "Test Client",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "client_id" in body
    # PydanticJSONResponse.render() serializes with exclude_none=True, so a null
    # client_secret (public client, token_endpoint_auth_method="none") is omitted
    # from the body entirely rather than serialized as `null`.
    assert body.get("client_secret") is None


async def test_mcp_unrecognized_bearer_still_falls_back_to_tier1(db):
    """A token mulchd never issued (garbage, or a bad manual token) keeps today's
    existing behavior: served as tier1, not a 401. This documents that this task
    deliberately does NOT change that case.

    Exercised at the resolve_mcp_tier level rather than a real POST /mcp round trip:
    the streamable-HTTP transport requires an Accept header (application/json and/or
    text/event-stream) that a plain client.post(json=...) doesn't send, and its session
    manager's run() may only be entered once per process — both make a raw HTTP
    round trip through the ASGI test transport unsuitable here. This matches the
    convention already used by the sibling assertions in tests/test_mcp_tiers.py.
    """
    from starlette.requests import Request

    from mulchd.main import resolve_mcp_tier
    from mulchd.mcp import McpTier

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"authorization", b"Bearer not-a-real-token")],
    }
    request = Request(scope)
    tier, ctx = await resolve_mcp_tier(request)
    assert tier == McpTier.TIER1
    assert ctx is None


async def test_mcp_expired_oauth_token_returns_401_with_www_authenticate(client, db):
    from datetime import UTC, datetime, timedelta

    from mulchd.auth import create_user
    from mulchd.mcp_auth import MulchdOAuthProvider, _hash
    from mulchd.models import OAuthClient, OAuthGrant, OAuthToken, Organization, Project, UserMembership

    user, _ = await create_user("dana", "Dana")
    org = await Organization.create(slug="acme4", display_name="Acme4")
    project = await Project.create(slug="demo4", display_name="Demo4", org=org)
    await UserMembership.create(user=user, project=project)
    client_row = await OAuthClient.create(client_id="cli-y", client_metadata={"client_id": "cli-y"})
    grant = await OAuthGrant.create(client=client_row, user=user, project=project)

    provider = MulchdOAuthProvider()
    tokens = await provider._issue_tokens(client_row.client_id, grant, ["mulchd"])
    # simulate expiry
    row = await OAuthToken.get(access_token_hash=_hash(tokens.access_token))
    row.access_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await row.save()

    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )
    assert resp.status_code == 401
    www_auth = resp.headers["www-authenticate"]
    assert 'error="invalid_token"' in www_auth
    assert "resource_metadata=" in www_auth


async def test_mcp_revoked_oauth_token_returns_401(client, db):
    from mulchd.auth import create_user
    from mulchd.mcp_auth import MulchdOAuthProvider
    from mulchd.models import OAuthClient, OAuthGrant, Organization, Project, UserMembership

    user, _ = await create_user("erin", "Erin")
    org = await Organization.create(slug="acme5", display_name="Acme5")
    project = await Project.create(slug="demo5", display_name="Demo5", org=org)
    await UserMembership.create(user=user, project=project)
    client_row = await OAuthClient.create(client_id="cli-z", client_metadata={"client_id": "cli-z"})
    grant = await OAuthGrant.create(client=client_row, user=user, project=project)

    provider = MulchdOAuthProvider()
    tokens = await provider._issue_tokens(client_row.client_id, grant, ["mulchd"])
    access_token = await provider.load_access_token(tokens.access_token)
    assert access_token is not None
    await provider.revoke_token(access_token)

    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )
    assert resp.status_code == 401


def test_mcp_oauth_invalid_issuer_url_degrades_gracefully():
    """
    This project's own default settings (MULCHD_HOST=0.0.0.0, no MULCHD_BASE_URL)
    resolve to an issuer URL the mcp SDK's RFC 8414 validation rejects (HTTPS
    required, with a localhost/127.0.0.1 carve-out this doesn't match). Since
    mcp_oauth_enabled defaults to True, a deployer who follows the example env
    file as-is must not have their entire app fail to start over this — OAuth AS
    routes should simply not register, with everything else (admin, /connect,
    tier1/tier2 MCP) unaffected.

    Run in a subprocess, not via importlib.reload(mulchd.main) in-process:
    reloading this module while other already-imported modules (conftest's
    `client` fixture, other test files' cached imports) still hold references to
    the old module objects corrupts shared global state (Tortoise's model
    registry, the mcp session managers' internal contextvars) in ways that broke
    unrelated tests elsewhere in the suite depending on run order — confirmed by
    trying exactly that approach first. A subprocess sidesteps it entirely: this
    process's own already-imported `mulchd.main` (used by every other test in
    this file via the `client` fixture) is never touched.
    """
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env["MULCHD_HOST"] = "0.0.0.0"
    env.pop("MULCHD_BASE_URL", None)
    env["MULCHD_SECRET_KEY"] = "test-secret-key"
    env["MULCHD_DB_URL"] = "sqlite://:memory:"

    result = subprocess.run(
        [sys.executable, "-c", "from mulchd.main import app; print('IMPORT_OK')"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "IMPORT_OK" in result.stdout
    assert "not registered" in result.stderr


async def test_resolve_mcp_tier_accepts_oauth_access_token(db):
    from mulchd.auth import create_user
    from mulchd.main import resolve_mcp_tier
    from mulchd.mcp import McpTier
    from mulchd.mcp_auth import MulchdOAuthProvider
    from mulchd.models import OAuthClient, OAuthGrant, Organization, Project, UserMembership
    from starlette.requests import Request

    user, _ = await create_user("carol", "Carol")
    org = await Organization.create(slug="acme3", display_name="Acme3")
    project = await Project.create(slug="demo3", display_name="Demo3", org=org)
    await UserMembership.create(user=user, project=project)
    client_row = await OAuthClient.create(client_id="cli-x", client_metadata={"client_id": "cli-x"})
    grant = await OAuthGrant.create(client=client_row, user=user, project=project)

    provider = MulchdOAuthProvider()
    tokens = await provider._issue_tokens(client_row.client_id, grant, ["mulchd"])

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"authorization", f"Bearer {tokens.access_token}".encode())],
    }
    request = Request(scope)
    tier, ctx = await resolve_mcp_tier(request)
    assert tier == McpTier.TIER2
    assert ctx is not None
    assert ctx.user.id == user.id
    assert ctx.project.id == project.id


def test_mcp_oauth_disabled_omits_well_known_routes():
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env["MULCHD_MCP_OAUTH_ENABLED"] = "false"
    env["MULCHD_SECRET_KEY"] = "test-secret-key"
    env["MULCHD_DB_URL"] = "sqlite://:memory:"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from mulchd.main import app; "
            "assert not [r for r in app.router.routes if getattr(r, 'path', '') "
            "== '/.well-known/oauth-authorization-server']; "
            "print('DISABLED_OK')",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "DISABLED_OK" in result.stdout


async def test_resolve_mcp_tier_clamps_role_to_grant_ceiling(db):
    """A WRITER member who authorized the client as READER must get READER
    access, even though their own membership role is more privileged."""
    from mulchd.auth import create_user
    from mulchd.main import resolve_mcp_tier
    from mulchd.mcp import McpTier
    from mulchd.mcp_auth import MulchdOAuthProvider
    from mulchd.models import OAuthClient, OAuthGrant, Organization, Project, Role, UserMembership
    from starlette.requests import Request

    user, _ = await create_user("gina", "Gina")
    org = await Organization.create(slug="acme8", display_name="Acme8")
    project = await Project.create(slug="demo8", display_name="Demo8", org=org)
    await UserMembership.create(user=user, project=project, role=Role.WRITER)
    client_row = await OAuthClient.create(client_id="cli-clamp", client_metadata={"client_id": "cli-clamp"})
    grant = await OAuthGrant.create(client=client_row, user=user, project=project, granted_role=Role.READER)

    provider = MulchdOAuthProvider()
    tokens = await provider._issue_tokens(client_row.client_id, grant, ["mulchd"])

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"authorization", f"Bearer {tokens.access_token}".encode())],
    }
    request = Request(scope)
    tier, ctx = await resolve_mcp_tier(request)
    assert tier == McpTier.TIER2
    assert ctx is not None
    assert ctx.role == Role.READER


async def test_resolve_mcp_tier_membership_demotion_still_wins_even_with_admin_grant(db):
    """A grant's ceiling can only restrict, never restore, access the membership
    itself no longer has — min_role must take the live membership role too."""
    from mulchd.auth import create_user
    from mulchd.main import resolve_mcp_tier
    from mulchd.mcp import McpTier
    from mulchd.mcp_auth import MulchdOAuthProvider
    from mulchd.models import OAuthClient, OAuthGrant, Organization, Project, Role, UserMembership
    from starlette.requests import Request

    user, _ = await create_user("harold", "Harold")
    org = await Organization.create(slug="acme9", display_name="Acme9")
    project = await Project.create(slug="demo9", display_name="Demo9", org=org)
    await UserMembership.create(user=user, project=project, role=Role.READER)
    client_row = await OAuthClient.create(client_id="cli-demote", client_metadata={"client_id": "cli-demote"})
    # granted as ADMIN back when the user was an admin member; membership has since
    # been demoted to READER without the grant being revisited.
    grant = await OAuthGrant.create(client=client_row, user=user, project=project, granted_role=Role.ADMIN)

    provider = MulchdOAuthProvider()
    tokens = await provider._issue_tokens(client_row.client_id, grant, ["mulchd"])

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"authorization", f"Bearer {tokens.access_token}".encode())],
    }
    request = Request(scope)
    _, ctx = await resolve_mcp_tier(request)
    assert ctx is not None
    assert ctx.role == Role.READER
