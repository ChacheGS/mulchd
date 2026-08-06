from __future__ import annotations

from tortoise import fields, models

from .identity import User
from .tenancy import Project


class ToolCall(models.Model):
    id = fields.IntField(primary_key=True)
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="tool_calls"
    )
    author: fields.ForeignKeyRelation[User] | None = fields.ForeignKeyField(
        "models.User", related_name="tool_calls", null=True
    )
    tool = fields.CharField(max_length=64)
    client = fields.CharField(max_length=64, default="unknown")
    # mulchd's v1 mcp SDK only ever spoke LATEST_PROTOCOL_VERSION="2025-11-25" —
    # the default backfills every pre-migration row with that value via the
    # generated migration's DDL. This is a best-effort label, not a certainty:
    # the field wasn't tracked before this migration, so there's no way to
    # confirm whether an older client ever explicitly negotiated down to an
    # earlier version during its initialize handshake.
    protocol_version = fields.CharField(max_length=32, default="2025-11-25")
    called_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "tool_calls"


class RecordMeta(models.Model):
    """`ml`'s record IDs are content-derived (a short hash of type + an
    identifying field, not random — see mulch's generateRecordId), so two
    different projects can legitimately produce the same record_id. Uniqueness
    is per (project, record_id), not on record_id alone."""

    id = fields.IntField(primary_key=True)
    record_id = fields.CharField(max_length=32)  # mx-xxxxxx
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
        unique_together = (("project", "record_id"),)


class RecordEvent(models.Model):
    """Out-of-band audit log for every mutating action on a record."""

    # Note: aerich (0.9.2) does not diff on_delete changes — `aerich migrate`
    # reports "No changes detected" even when this differs from what's in the
    # DB. Any future on_delete change here needs a hand-written migration
    # (ALTER TABLE ... DROP/ADD CONSTRAINT), not an auto-generated one.
    id = fields.IntField(primary_key=True)
    record_id = fields.CharField(max_length=32)  # mx-xxxxxx; not FK, survives deletes
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="record_events"
    )
    domain = fields.CharField(max_length=64)  # for "move", the target domain
    source_domain = fields.CharField(max_length=64, null=True, default=None)  # "move" only
    actor: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="record_events", on_delete=fields.RESTRICT
    )
    action = fields.CharField(max_length=16)  # "write" | "edit" | "delete" | "move"
    client = fields.CharField(max_length=64, default="unknown")
    session_id = fields.UUIDField(null=True)
    at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "record_events"


class RecordEdit(models.Model):
    """Before-snapshot for every edit_record call."""

    # Note: aerich (0.9.2) does not diff on_delete changes — `aerich migrate`
    # reports "No changes detected" even when this differs from what's in the
    # DB. Any future on_delete change here needs a hand-written migration
    # (ALTER TABLE ... DROP/ADD CONSTRAINT), not an auto-generated one.
    id = fields.IntField(primary_key=True)
    record_id = fields.CharField(max_length=32)
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="record_edits"
    )
    domain = fields.CharField(max_length=64)
    actor: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="record_edits", on_delete=fields.RESTRICT
    )
    # {field: old_value} for fields that changed.
    # Tortoise JSONField stub doesn't parametrize its value type.
    before_snapshot = fields.JSONField()  # pyright: ignore[reportUnknownVariableType]
    client = fields.CharField(max_length=64, default="unknown")
    session_id = fields.UUIDField(null=True)
    at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "record_edits"
