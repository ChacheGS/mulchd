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
    token_hash = fields.CharField(max_length=64)  # sha256 hex of bearer token
    active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "users"


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
