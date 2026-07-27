import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull
from mcp.shared.auth import OAuthToken as SdkOAuthToken

from .models import OAuthClient, OAuthCode, OAuthGrant, OAuthToken

ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=30)
AUTH_CODE_TTL = timedelta(minutes=5)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _generate_secret() -> str:
    return secrets.token_urlsafe(32)


class MulchdOAuthProvider(OAuthAuthorizationServerProvider):
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        row = await OAuthClient.filter(client_id=client_id).first()
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate(row.client_metadata)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await OAuthClient.create(
            client_id=client_info.client_id,
            client_metadata=client_info.model_dump(mode="json"),
        )

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        query = urlencode(
            {
                "client_id": client.client_id,
                "redirect_uri": str(params.redirect_uri),
                "code_challenge": params.code_challenge,
                "state": params.state or "",
                "scope": " ".join(params.scopes or []),
            }
        )
        return f"/connect/oauth-consent?{query}"
