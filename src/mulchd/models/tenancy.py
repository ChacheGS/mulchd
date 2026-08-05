from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from tortoise import fields, models

if TYPE_CHECKING:
    from .identity import User


class Role(StrEnum):
    READER = "reader"
    WRITER = "writer"
    ADMIN = "admin"


_ROLE_RANK: dict[Role, int] = {Role.READER: 0, Role.WRITER: 1, Role.ADMIN: 2}


def min_role(a: Role, b: Role) -> Role:
    """The more restrictive of two roles, by rank (READER < WRITER < ADMIN)."""
    return a if _ROLE_RANK[a] <= _ROLE_RANK[b] else b


def roles_up_to(ceiling: Role) -> list[Role]:
    """All roles at or below `ceiling`, ordered from most to least privileged."""
    return [
        r for r in (Role.ADMIN, Role.WRITER, Role.READER) if _ROLE_RANK[r] <= _ROLE_RANK[ceiling]
    ]


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
