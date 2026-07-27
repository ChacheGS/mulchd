from __future__ import annotations

from datetime import UTC, datetime

from tortoise import fields, models

from .tenancy import Project, Role


class User(models.Model):
    id = fields.IntField(primary_key=True)
    username = fields.CharField(max_length=64, unique=True)
    display_name = fields.CharField(max_length=128)
    email = fields.CharField(max_length=255, null=True, unique=True, default=None)
    token_hash = fields.CharField(max_length=64)  # sha256 hex of bearer token
    active = fields.BooleanField(default=True)
    first_login_at = fields.DatetimeField(null=True, default=None)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "users"


class OAuthIdentity(models.Model):
    id = fields.IntField(primary_key=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="oauth_identities"
    )
    provider = fields.CharField(max_length=32)   # "github" | "oidc"
    sub = fields.CharField(max_length=255)        # provider's immutable user ID
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "oauth_identities"
        unique_together = (("provider", "sub"),)


class InviteLink(models.Model):
    id = fields.IntField(primary_key=True)
    token = fields.CharField(max_length=64, unique=True)
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="invite_links"
    )
    role = fields.CharEnumField(Role, max_length=16, default=Role.WRITER)
    max_uses = fields.IntField(null=True, default=None)
    use_count = fields.IntField(default=0)
    expires_at = fields.DatetimeField(null=True, default=None)
    allowed_email_domains = fields.JSONField(null=True, default=None)
    revoked = fields.BooleanField(default=False)
    created_by: fields.ForeignKeyRelation[User] | None = fields.ForeignKeyField(
        "models.User", related_name="created_invites", null=True, default=None
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    @property
    def status(self) -> str:
        if self.revoked:
            return "revoked"
        if self.expires_at is not None:
            expires = self.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires < datetime.now(UTC):
                return "expired"
        if self.max_uses is not None and self.use_count >= self.max_uses:
            return "exhausted"
        return "active"

    class Meta:
        table = "invite_links"


class InviteUse(models.Model):
    id = fields.IntField(primary_key=True)
    invite: fields.ForeignKeyRelation[InviteLink] = fields.ForeignKeyField(
        "models.InviteLink", related_name="uses"
    )
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="invite_uses"
    )
    used_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "invite_uses"
