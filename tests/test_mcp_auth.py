import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


async def test_register_client_then_get_client_roundtrip(db):
    from mcp.shared.auth import OAuthClientMetadata

    from mulchd.mcp_auth import MulchdOAuthProvider

    provider = MulchdOAuthProvider()
    metadata = OAuthClientMetadata(
        redirect_uris=["http://localhost:1234/cb"],
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
    assert str(fetched.redirect_uris[0]) == "http://localhost:1234/cb"


async def test_get_client_unknown_returns_none(db):
    from mulchd.mcp_auth import MulchdOAuthProvider

    provider = MulchdOAuthProvider()
    assert await provider.get_client("does-not-exist") is None


async def test_authorize_redirects_to_consent_page(db):
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
    params = AuthorizationParams(
        state="xyz",
        scopes=["mulchd"],
        code_challenge="challenge123",
        redirect_uri="http://localhost:1234/cb",
        redirect_uri_provided_explicitly=True,
    )
    url = await provider.authorize(client, params)
    assert url.startswith("/connect/oauth-consent?")
    assert "client_id=client-9" in url
    assert "code_challenge=challenge123" in url
    assert "state=xyz" in url
