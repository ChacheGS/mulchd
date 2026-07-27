from __future__ import annotations

from tortoise import fields, models

from .identity import User
from .tenancy import Project


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
