import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from pydantic import AnyUrl

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
        # row.client_id is the authoritative business key; the stored client_metadata
        # blob may carry a stale or placeholder value (e.g. captured before the real
        # client_id was assigned), so it must not be trusted over the row itself.
        return OAuthClientInformationFull.model_validate({**row.client_metadata, "client_id": row.client_id})

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

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        assert client.client_id is not None, "registered clients always have a client_id"
        row = (
            await OAuthCode.filter(code_hash=_hash(authorization_code), client_id=client.client_id, used=False)
            .select_related("grant")
            .first()
        )
        if row is None:
            return None
        expires_at = row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
        if expires_at < datetime.now(UTC):
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=row.scope.split() if row.scope else [],
            expires_at=expires_at.timestamp(),
            client_id=client.client_id,
            code_challenge=row.code_challenge,
            redirect_uri=AnyUrl(row.redirect_uri),
            redirect_uri_provided_explicitly=True,
            subject=str(row.grant.user_id),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> SdkOAuthToken:
        assert client.client_id is not None, "registered clients always have a client_id"
        row = (
            await OAuthCode.filter(code_hash=_hash(authorization_code.code), client_id=client.client_id)
            .select_related("grant")
            .first()
        )
        if row is None or row.used:
            raise TokenError(error="invalid_grant", error_description="authorization code already used")
        # Atomic compare-and-swap, not a read-then-write: two concurrent exchanges of the
        # same code must not both succeed. update() only flips rows still unused, and
        # returns the affected count — a second racing request sees 0 and is rejected,
        # even though its earlier `row.used` read (above) also observed False.
        claimed = await OAuthCode.filter(id=row.id, used=False).update(used=True)
        if claimed == 0:
            raise TokenError(error="invalid_grant", error_description="authorization code already used")
        return await self._issue_tokens(client.client_id, row.grant, authorization_code.scopes)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        assert client.client_id is not None, "registered clients always have a client_id"
        row = (
            await OAuthToken.filter(
                refresh_token_hash=_hash(refresh_token), client_id=client.client_id, revoked=False
            )
            .select_related("grant")
            .first()
        )
        if row is None:
            return None
        expires_at = row.refresh_expires_at
        expires_at = expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=row.scope.split() if row.scope else [],
            expires_at=int(expires_at.timestamp()),
            subject=str(row.grant.user_id),
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> SdkOAuthToken:
        assert client.client_id is not None, "registered clients always have a client_id"
        row = (
            await OAuthToken.filter(
                refresh_token_hash=_hash(refresh_token.token), client_id=client.client_id, revoked=False
            )
            .select_related("grant")
            .first()
        )
        if row is None:
            raise TokenError(error="invalid_grant", error_description="refresh token not found")
        # Atomic compare-and-swap: two concurrent refreshes of the same token must not
        # both succeed and mint separate token pairs. See exchange_authorization_code
        # for the same pattern and rationale.
        claimed = await OAuthToken.filter(id=row.id, revoked=False).update(revoked=True)
        if claimed == 0:
            raise TokenError(error="invalid_grant", error_description="refresh token not found")
        return await self._issue_tokens(client.client_id, row.grant, scopes or refresh_token.scopes)

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = await OAuthToken.filter(access_token_hash=_hash(token), revoked=False).select_related("grant").first()
        if row is None:
            return None
        expires_at = row.access_expires_at
        expires_at = expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at
        if expires_at < datetime.now(UTC):
            return None
        return AccessToken(
            token=token,
            client_id=row.client_id,
            scopes=row.scope.split() if row.scope else [],
            expires_at=int(expires_at.timestamp()),
            subject=str(row.grant.user_id),
            claims={"project_id": row.grant.project_id, "granted_role": str(row.grant.granted_role)},
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        token_hash = _hash(token.token)
        await OAuthToken.filter(access_token_hash=token_hash).update(revoked=True)
        await OAuthToken.filter(refresh_token_hash=token_hash).update(revoked=True)

    async def _issue_tokens(self, client_id: str, grant: OAuthGrant, scopes: list[str]) -> SdkOAuthToken:
        # client_id must be the caller's OAuthClientInformationFull.client_id (string) —
        # NOT grant.client_id, which is Tortoise's raw FK column and holds the related
        # OAuthClient row's integer primary key, not its client_id string. Every caller
        # of this method already has the correct string in scope as `client.client_id`.
        access_token = _generate_secret()
        refresh_token = _generate_secret()
        now = datetime.now(UTC)
        scope_str = " ".join(scopes) if scopes else None
        await OAuthToken.create(
            access_token_hash=_hash(access_token),
            refresh_token_hash=_hash(refresh_token),
            client_id=client_id,
            grant=grant,
            scope=scope_str,
            access_expires_at=now + ACCESS_TOKEN_TTL,
            refresh_expires_at=now + REFRESH_TOKEN_TTL,
        )
        return SdkOAuthToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
            scope=scope_str,
        )


async def is_known_oauth_token(token: str) -> bool:
    """
    True if this token hash matches an OAuthToken row mulchd itself issued, regardless
    of whether it's since expired or been revoked. Used to distinguish "this was ours,
    but it's no longer valid" (→ 401 invalid_token, so OAuth clients know to refresh)
    from "mulchd never issued this" (→ existing tier1 fallback, unchanged).
    """
    return await OAuthToken.filter(access_token_hash=_hash(token)).exists()
