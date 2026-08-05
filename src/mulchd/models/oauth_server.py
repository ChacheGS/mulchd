from __future__ import annotations

from tortoise import fields, models

from .identity import User
from .tenancy import Project, Role


class OAuthClient(models.Model):
    """A dynamically-registered MCP client (RFC 7591)."""

    id = fields.IntField(primary_key=True)
    client_id = fields.CharField(max_length=64, unique=True)
    # Full OAuthClientInformationFull as returned by mcp's registration handler —
    # includes client_secret in plaintext when the SDK issues one (confidential
    # clients only; public clients register with token_endpoint_auth_method="none"
    # and get no secret). The SDK's own ClientAuthenticator compares this value
    # directly via hmac.compare_digest, so it cannot be stored hashed.
    client_metadata = fields.JSONField()  # pyright: ignore[reportUnknownVariableType]  # Tortoise JSONField stub doesn't parametrize its value type
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "oauth_clients"


class OAuthGrant(models.Model):
    """A remembered user consent for one client, scoped to one project."""

    id = fields.IntField(primary_key=True)
    client: fields.ForeignKeyRelation[OAuthClient] = fields.ForeignKeyField(
        "models.OAuthClient", related_name="grants", on_delete=fields.CASCADE
    )
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="oauth_grants", on_delete=fields.CASCADE
    )
    user_id: int
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="oauth_grants", on_delete=fields.CASCADE
    )
    project_id: int
    # Ceiling on the role this client is authorized as, chosen at consent time and
    # capped server-side to the granting user's own membership role. Defaults to
    # ADMIN (the rank ceiling) so grants created before this field existed, and any
    # created without specifying it, keep prior behavior: no ceiling beyond the
    # live membership role checked at request time (see min_role in tenancy.py).
    granted_role = fields.CharEnumField(Role, max_length=16, default=Role.ADMIN)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "oauth_grants"
        unique_together = (("client", "user"),)


class OAuthCode(models.Model):
    """A short-lived, single-use authorization code."""

    id = fields.IntField(primary_key=True)
    code_hash = fields.CharField(max_length=64, unique=True)
    client_id = fields.CharField(max_length=64)
    grant: fields.ForeignKeyRelation[OAuthGrant] = fields.ForeignKeyField(
        "models.OAuthGrant", related_name="codes", on_delete=fields.CASCADE
    )
    redirect_uri = fields.CharField(max_length=512)
    code_challenge = fields.CharField(max_length=128)
    scope = fields.CharField(max_length=255, null=True, default=None)
    expires_at = fields.DatetimeField()
    used = fields.BooleanField(default=False)

    class Meta:
        table = "oauth_codes"


class OAuthToken(models.Model):
    """An issued access/refresh token pair."""

    id = fields.IntField(primary_key=True)
    access_token_hash = fields.CharField(max_length=64, unique=True)
    refresh_token_hash = fields.CharField(max_length=64, unique=True)
    client_id = fields.CharField(max_length=64)
    grant: fields.ForeignKeyRelation[OAuthGrant] = fields.ForeignKeyField(
        "models.OAuthGrant", related_name="tokens", on_delete=fields.CASCADE
    )
    scope = fields.CharField(max_length=255, null=True, default=None)
    access_expires_at = fields.DatetimeField()
    refresh_expires_at = fields.DatetimeField()
    revoked = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "oauth_tokens"
