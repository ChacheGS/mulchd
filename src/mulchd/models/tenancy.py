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
