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
    await provider.revoke_token(access_token)

    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )
    assert resp.status_code == 401


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
