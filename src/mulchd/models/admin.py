from __future__ import annotations

from enum import StrEnum

from tortoise import fields, models

from .identity import User
from .tenancy import Organization, Project


class AdminRole(StrEnum):
    SUPERADMIN = "superadmin"


class AdminGrant(models.Model):
    # Note: aerich (0.9.2) does not diff on_delete changes — `aerich migrate`
    # reports "No changes detected" even when this differs from what's in the
    # DB. Any future on_delete change here needs a hand-written migration
    # (ALTER TABLE ... DROP/ADD CONSTRAINT), not an auto-generated one.
    id = fields.IntField(primary_key=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="admin_grants", on_delete=fields.RESTRICT
    )
    role = fields.CharEnumField(AdminRole, max_length=16, default=AdminRole.SUPERADMIN)
    org: fields.ForeignKeyRelation[Organization] | None = fields.ForeignKeyField(
        "models.Organization", related_name="org_admin_grants", null=True, default=None
    )
    granted_by: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="granted_admin_grants", on_delete=fields.RESTRICT
    )
    granted_at = fields.DatetimeField(auto_now_add=True)
    revoked_by: fields.ForeignKeyRelation[User] | None = fields.ForeignKeyField(
        "models.User",
        related_name="revoked_admin_grants",
        null=True,
        default=None,
        on_delete=fields.RESTRICT,
    )
    revoked_at = fields.DatetimeField(null=True, default=None)

    class Meta:
        table = "admin_grants"


class InstanceEventCategory(StrEnum):
    ADMIN_GRANTED = "admin_granted"
    ADMIN_REVOKED = "admin_revoked"
    MEMBERSHIP_ADDED = "membership_added"
    MEMBERSHIP_REMOVED = "membership_removed"
    FIRST_LOGIN = "first_login"
    OAUTH_LINKED = "oauth_linked"
    TOKEN_RESET = "token_reset"
    ORG_CREATED = "org_created"
    PROJECT_CREATED = "project_created"
    USER_CREATED = "user_created"
    USER_DEACTIVATED = "user_deactivated"
    INVITE_CREATED = "invite_created"
    INVITE_REVOKED = "invite_revoked"


class InstanceEvent(models.Model):
    # Note: aerich (0.9.2) does not diff on_delete changes — `aerich migrate`
    # reports "No changes detected" even when this differs from what's in the
    # DB. Any future on_delete change here needs a hand-written migration
    # (ALTER TABLE ... DROP/ADD CONSTRAINT), not an auto-generated one.
    id = fields.IntField(primary_key=True)
    category = fields.CharEnumField(InstanceEventCategory, max_length=32)
    actor: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="instance_events_acted", on_delete=fields.RESTRICT
    )
    subject_user: fields.ForeignKeyRelation[User] | None = fields.ForeignKeyField(
        "models.User",
        related_name="instance_events_about",
        null=True,
        default=None,
        on_delete=fields.RESTRICT,
    )
    project: fields.ForeignKeyRelation[Project] | None = fields.ForeignKeyField(
        "models.Project", related_name="instance_events", null=True, default=None, on_delete=fields.RESTRICT
    )
    detail = fields.JSONField(null=True, default=None)
    at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "instance_events"
