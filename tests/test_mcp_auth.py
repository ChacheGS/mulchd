import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


async def _make_client_grant(project=None):
    from mulchd.auth import create_user
    from mulchd.models import OAuthClient, OAuthGrant, Organization, Project

    user, _ = await create_user(f"user-{secrets_suffix()}", "User")
    org = await Organization.create(slug=f"org-{secrets_suffix()}", display_name="Org")
    project = project or await Project.create(slug=f"proj-{secrets_suffix()}", display_name="Proj", org=org)
    client = await OAuthClient.create(
        client_id=f"client-{secrets_suffix()}",
        client_metadata={
            "client_id": "placeholder",
            "redirect_uris": ["http://localhost/cb"],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )
    grant = await OAuthGrant.create(client=client, user=user, project=project)
    return user, project, client, grant


def secrets_suffix() -> str:
    import secrets

    return secrets.token_hex(4)


async def test_exchange_authorization_code_issues_tokens(db):
    from datetime import UTC, datetime, timedelta

    from mulchd.mcp_auth import MulchdOAuthProvider, hash_token
    from mulchd.models import OAuthCode, OAuthToken

    user, project, client_row, grant = await _make_client_grant()
    provider = MulchdOAuthProvider()
    client = await provider.get_client(client_row.client_id)
    assert client is not None
    assert client.client_id is not None

    code_row = await OAuthCode.create(
        code_hash=hash_token("raw-code-1"),
        client_id=client_row.client_id,
        grant=grant,
        redirect_uri="http://localhost/cb",
        code_challenge="chal",
        scope="mulchd",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    auth_code = await provider.load_authorization_code(client, "raw-code-1")
    assert auth_code is not None
    assert auth_code.client_id == client_row.client_id

    tokens = await provider.exchange_authorization_code(client, auth_code)
    assert tokens.access_token
    assert tokens.refresh_token

    await code_row.refresh_from_db()
    assert code_row.used is True

    # replay is rejected
    assert await provider.load_authorization_code(client, "raw-code-1") is None

    # regression: OAuthToken.client_id must be the string client_id, not grant's raw FK int
    issued = await OAuthToken.get(access_token_hash=hash_token(tokens.access_token))
    assert issued.client_id == client_row.client_id


async def test_load_access_token_carries_project_claim(db):
    from mulchd.mcp_auth import MulchdOAuthProvider

    user, project, client_row, grant = await _make_client_grant()
    provider = MulchdOAuthProvider()
    client = await provider.get_client(client_row.client_id)
    assert client is not None
    assert client.client_id is not None
    tokens = await provider._issue_tokens(client.client_id, grant, ["mulchd"])

    access_token = await provider.load_access_token(tokens.access_token)
    assert access_token is not None
    assert access_token.subject == str(user.id)
    assert access_token.claims is not None
    assert access_token.claims["project_id"] == project.id


async def test_refresh_token_rotation(db):
    from mulchd.mcp_auth import MulchdOAuthProvider

    user, project, client_row, grant = await _make_client_grant()
    provider = MulchdOAuthProvider()
    client = await provider.get_client(client_row.client_id)
    assert client is not None
    assert client.client_id is not None
    tokens = await provider._issue_tokens(client.client_id, grant, ["mulchd"])
    assert tokens.refresh_token is not None

    refresh_token = await provider.load_refresh_token(client, tokens.refresh_token)
    assert refresh_token is not None

    new_tokens = await provider.exchange_refresh_token(client, refresh_token, ["mulchd"])
    assert new_tokens.access_token != tokens.access_token
    assert new_tokens.refresh_token != tokens.refresh_token

    # old refresh token no longer loads
    assert await provider.load_refresh_token(client, tokens.refresh_token) is None


async def test_revoke_token(db):
    from mulchd.mcp_auth import MulchdOAuthProvider

    user, project, client_row, grant = await _make_client_grant()
    provider = MulchdOAuthProvider()
    client = await provider.get_client(client_row.client_id)
    assert client is not None
    assert client.client_id is not None
    tokens = await provider._issue_tokens(client.client_id, grant, ["mulchd"])

    access_token = await provider.load_access_token(tokens.access_token)
    assert access_token is not None
    await provider.revoke_token(access_token)

    assert await provider.load_access_token(tokens.access_token) is None


async def test_revoke_token_accepts_refresh_token(db):
    """revoke_token's signature is AccessToken | RefreshToken — cover the refresh-token
    branch too, not just access tokens."""
    from mulchd.mcp_auth import MulchdOAuthProvider

    user, project, client_row, grant = await _make_client_grant()
    provider = MulchdOAuthProvider()
    client = await provider.get_client(client_row.client_id)
    assert client is not None
    assert client.client_id is not None
    tokens = await provider._issue_tokens(client.client_id, grant, ["mulchd"])
    assert tokens.refresh_token is not None

    refresh_token = await provider.load_refresh_token(client, tokens.refresh_token)
    assert refresh_token is not None
    await provider.revoke_token(refresh_token)

    assert await provider.load_refresh_token(client, tokens.refresh_token) is None
    # revoking via the refresh token also invalidates the paired access token
    assert await provider.load_access_token(tokens.access_token) is None


async def test_load_access_token_rejects_expired_token(db):
    from datetime import UTC, datetime, timedelta

    from mulchd.mcp_auth import MulchdOAuthProvider, hash_token
    from mulchd.models import OAuthToken

    user, project, client_row, grant = await _make_client_grant()
    provider = MulchdOAuthProvider()
    client = await provider.get_client(client_row.client_id)
    assert client is not None
    assert client.client_id is not None
    tokens = await provider._issue_tokens(client.client_id, grant, ["mulchd"])
    assert tokens.refresh_token is not None

    row = await OAuthToken.get(access_token_hash=hash_token(tokens.access_token))
    row.access_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await row.save()

    assert await provider.load_access_token(tokens.access_token) is None


async def test_load_refresh_token_reports_expiry_but_does_not_self_reject(db):
    """
    Unlike load_access_token, load_refresh_token intentionally does not reject an
    expired token itself — the mcp SDK's own TokenHandler checks
    RefreshToken.expires_at after calling this method (see token.py's refresh grant
    branch). This pins that division of responsibility: the row's real (past)
    expiry must still be reported accurately so the SDK's own check can act on it.
    """
    from datetime import UTC, datetime, timedelta

    from mulchd.mcp_auth import MulchdOAuthProvider, hash_token
    from mulchd.models import OAuthToken

    user, project, client_row, grant = await _make_client_grant()
    provider = MulchdOAuthProvider()
    client = await provider.get_client(client_row.client_id)
    assert client is not None
    assert client.client_id is not None
    tokens = await provider._issue_tokens(client.client_id, grant, ["mulchd"])
    assert tokens.refresh_token is not None

    past_expiry = datetime.now(UTC) - timedelta(minutes=1)
    row = await OAuthToken.get(refresh_token_hash=hash_token(tokens.refresh_token))
    row.refresh_expires_at = past_expiry
    await row.save()

    refresh_token = await provider.load_refresh_token(client, tokens.refresh_token)
    assert refresh_token is not None
    assert refresh_token.expires_at == int(past_expiry.timestamp())


async def test_register_client_then_get_client_roundtrip(db):
    from pydantic import AnyUrl

    from mcp.shared.auth import OAuthClientMetadata

    from mulchd.mcp_auth import MulchdOAuthProvider

    provider = MulchdOAuthProvider()
    metadata = OAuthClientMetadata(
        redirect_uris=[AnyUrl("http://localhost:1234/cb")],
        client_name="Test Client",
        token_endpoint_auth_method="none",
    )
    # register_client expects an OAuthClientInformationFull, matching what the SDK's
    # RegistrationHandler builds before calling us. client_id is only a field on the
    # full subclass, not on OAuthClientMetadata, so it must be set at construction
    # time here rather than via metadata.model_copy(update=...) (which would silently
    # drop it, since model_dump() only serializes declared fields of the base class).
    from mcp.shared.auth import OAuthClientInformationFull

    full = OAuthClientInformationFull(client_id="abc123", **metadata.model_dump())
    await provider.register_client(full)

    fetched = await provider.get_client("abc123")
    assert fetched is not None
    assert fetched.client_id == "abc123"
    assert fetched.client_name == "Test Client"
    assert fetched.redirect_uris is not None
    assert str(fetched.redirect_uris[0]) == "http://localhost:1234/cb"


async def test_get_client_unknown_returns_none(db):
    from mulchd.mcp_auth import MulchdOAuthProvider

    provider = MulchdOAuthProvider()
    assert await provider.get_client("does-not-exist") is None


async def test_authorize_redirects_to_consent_page(db):
    from pydantic import AnyUrl

    from mcp.server.auth.provider import AuthorizationParams

    from mulchd.mcp_auth import MulchdOAuthProvider
    from mulchd.models import OAuthClient

    provider = MulchdOAuthProvider()
    client_row = await OAuthClient.create(
        client_id="client-9",
        client_metadata={
            "client_id": "client-9",
            "redirect_uris": ["http://localhost:1234/cb"],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )
    client = await provider.get_client(client_row.client_id)
    assert client is not None
    assert client.client_id is not None
    params = AuthorizationParams(
        state="xyz",
        scopes=["mulchd"],
        code_challenge="challenge123",
        redirect_uri=AnyUrl("http://localhost:1234/cb"),
        redirect_uri_provided_explicitly=True,
    )
    url = await provider.authorize(client, params)
    assert url.startswith("/connect/oauth-consent?")
    assert "client_id=client-9" in url
    assert "code_challenge=challenge123" in url
    assert "state=xyz" in url


async def test_load_access_token_carries_granted_role_claim(db):
    from mulchd.mcp_auth import MulchdOAuthProvider
    from mulchd.models import Role

    user, project, client_row, grant = await _make_client_grant()
    grant.granted_role = Role.READER
    await grant.save()

    provider = MulchdOAuthProvider()
    client = await provider.get_client(client_row.client_id)
    assert client is not None
    assert client.client_id is not None
    tokens = await provider._issue_tokens(client.client_id, grant, ["mulchd"])

    access_token = await provider.load_access_token(tokens.access_token)
    assert access_token is not None
    assert access_token.claims is not None
    assert access_token.claims["granted_role"] == "reader"
