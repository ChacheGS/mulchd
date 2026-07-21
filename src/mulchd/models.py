from datetime import UTC, datetime
from enum import StrEnum

from tortoise import fields, models


class Role(StrEnum):
    READER = "reader"
    WRITER = "writer"
    ADMIN = "admin"


class Organization(models.Model):
    id = fields.IntField(primary_key=True)
    slug = fields.CharField(max_length=64, unique=True)
    display_name = fields.CharField(max_length=128)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "organizations"


class Project(models.Model):
    id = fields.IntField(primary_key=True)
    slug = fields.CharField(max_length=64)
    display_name = fields.CharField(max_length=128)
    knowledge_language = fields.CharField(max_length=16, null=True, default=None)
    org: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField(
        "models.Organization", related_name="projects"
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "projects"
        unique_together = (("org", "slug"),)


class User(models.Model):
    id = fields.IntField(primary_key=True)
    username = fields.CharField(max_length=64, unique=True)
    display_name = fields.CharField(max_length=128)
    email = fields.CharField(max_length=255, null=True, unique=True, default=None)
    token_hash = fields.CharField(max_length=64)  # sha256 hex of bearer token
    active = fields.BooleanField(default=True)
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


class UserMembership(models.Model):
    id = fields.IntField(primary_key=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="memberships"
    )
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="memberships"
    )
    role = fields.CharEnumField(Role, max_length=16, default=Role.WRITER)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_memberships"
        unique_together = (("user", "project"),)


class AdminRole(StrEnum):
    SUPERADMIN = "superadmin"


class AdminGrant(models.Model):
    id = fields.IntField(primary_key=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="admin_grants"
    )
    role = fields.CharEnumField(AdminRole, max_length=16, default=AdminRole.SUPERADMIN)
    org: fields.ForeignKeyRelation[Organization] | None = fields.ForeignKeyField(
        "models.Organization", related_name="admin_grants", null=True, default=None
    )
    granted_by: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="granted_admin_grants"
    )
    granted_at = fields.DatetimeField(auto_now_add=True)
    revoked_by: fields.ForeignKeyRelation[User] | None = fields.ForeignKeyField(
        "models.User", related_name="revoked_admin_grants", null=True, default=None
    )
    revoked_at = fields.DatetimeField(null=True, default=None)

    class Meta:
        table = "admin_grants"


class ProjectToken(models.Model):
    id = fields.IntField(primary_key=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="project_tokens"
    )
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="tokens"
    )
    token_hash = fields.CharField(max_length=64, unique=True)
    label = fields.CharField(max_length=128, default="")
    created_at = fields.DatetimeField(auto_now_add=True)
    active = fields.BooleanField(default=True)

    class Meta:
        table = "project_tokens"


class ToolCall(models.Model):
    id = fields.IntField(primary_key=True)
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="tool_calls"
    )
    author: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="tool_calls", null=True
    )
    tool = fields.CharField(max_length=64)
    client = fields.CharField(max_length=64, default="unknown")
    called_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "tool_calls"


class RecordMeta(models.Model):
    record_id = fields.CharField(max_length=32, primary_key=True)  # mx-xxxxxx
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="records"
    )
    domain = fields.CharField(max_length=64)
    author: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="records"
    )
    session_id = fields.UUIDField()
    client = fields.CharField(max_length=64, default="unknown")
    written_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "record_meta"


class RecordEvent(models.Model):
    """Out-of-band audit log for every mutating action on a record."""

    id = fields.IntField(primary_key=True)
    record_id = fields.CharField(max_length=32)  # mx-xxxxxx; not FK, survives deletes
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="record_events"
    )
    domain = fields.CharField(max_length=64)
    actor: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="record_events"
    )
    action = fields.CharField(max_length=16)  # "write" | "edit" | "delete"
    client = fields.CharField(max_length=64, default="unknown")
    session_id = fields.UUIDField(null=True)
    at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "record_events"


class RecordEdit(models.Model):
    """Before-snapshot for every edit_record call."""

    id = fields.IntField(primary_key=True)
    record_id = fields.CharField(max_length=32)
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="record_edits"
    )
    domain = fields.CharField(max_length=64)
    actor: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="record_edits"
    )
    before_snapshot = fields.JSONField()  # {field: old_value} for fields that changed
    client = fields.CharField(max_length=64, default="unknown")
    session_id = fields.UUIDField(null=True)
    at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "record_edits"
