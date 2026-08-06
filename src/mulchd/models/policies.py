from __future__ import annotations

from tortoise import fields, models

from .identity import User
from .tenancy import Project


class ProjectPolicy(models.Model):
    """A runtime override for one named policy, scoped to one project.

    A row only exists once an admin has explicitly overridden a policy through
    the admin UI — no row means "use the environment variable's value, or the
    code default" (see src/mulchd/policies.py's resolve_policy for the full
    precedence order). `value` is deliberately untyped JSON since the registry,
    not the schema, owns each policy's real type.

    `value` is stored as a single-element list (`[<value>]`), not the bare value
    itself. Tortoise's JSONField round-trips any assigned str/bytes value through
    its JSON decoder immediately on assignment (not just on DB read), so a bare
    top-level string like "enforce" fails validation — it isn't valid JSON on its
    own; only a quoted JSON string, a number, a bool, a list, or a dict works as a
    top-level JSONField value here. Wrapping in a single-element list sidesteps
    this for every value type uniformly, including future policies. Callers
    reading/writing this field (see src/mulchd/policies.py, added in a later task)
    are responsible for wrapping on write and unwrapping on read.
    """

    id = fields.IntField(primary_key=True)
    project: fields.ForeignKeyRelation[Project] = fields.ForeignKeyField(
        "models.Project", related_name="policies"
    )
    key = fields.CharField(max_length=64)
    # Tortoise JSONField stub doesn't parametrize its value type.
    value = fields.JSONField()  # pyright: ignore[reportUnknownVariableType]
    updated_at = fields.DatetimeField(auto_now=True)
    updated_by: fields.ForeignKeyRelation[User] | None = fields.ForeignKeyField(
        "models.User", null=True, related_name="policy_changes", on_delete=fields.SET_NULL
    )

    class Meta:
        table = "project_policies"
        unique_together = (("project", "key"),)
