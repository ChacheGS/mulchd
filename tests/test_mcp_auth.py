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
