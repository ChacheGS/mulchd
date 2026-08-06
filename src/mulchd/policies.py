"""
Per-project, runtime-configurable behavioral policies.

Each policy is seedable from an environment variable at deploy time and
refinable afterward through the admin UI. A policy's env var value is either
the plain value or `ro:<value>` — the `ro:` prefix locks that policy
instance-wide to this value; the admin UI cannot override it while the prefix
is present. See resolve_policy for the full precedence order.

This module deliberately does not depend on mulchd.mcp — it's read from both
the MCP tool-dispatch layer and the admin UI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Literal, cast

from dotenv import dotenv_values

from .config import Settings
from .models import Project, ProjectPolicy

# Same file pydantic-settings already loads MULCHD_* values from (see
# Settings.model_config) — read from here so a policy env var set only in
# .env, not the real process environment, still gets a value at all.
# pydantic-settings types env_file as str | PathLike | Sequence[...] | None
# for the multi-file case it supports; mulchd only ever configures one path.
_DOTENV_PATH = cast("str | os.PathLike[str]", Settings.model_config.get("env_file", ".env"))
assert isinstance(_DOTENV_PATH, (str, os.PathLike)), (
    f"policies.py assumes a single env_file path, got {_DOTENV_PATH!r} — "
    f"update _get_env to handle Settings.model_config's multi-file case"
)


def _get_env(name: str) -> str | None:
    """Real process env wins over .env, matching pydantic-settings' own
    documented precedence — .env is a fallback for values that were never
    exported into the environment at all."""
    value = os.environ.get(name)
    if value is not None:
        return value
    return dotenv_values(_DOTENV_PATH).get(name)


def _parse_enforcement(raw: str) -> str:
    if raw not in ("warn", "enforce"):
        raise ValueError(f"{raw!r} is not 'warn' or 'enforce'")
    return raw


def _parse_bool(raw: str) -> bool:
    if raw not in ("true", "false"):
        raise ValueError(f"{raw!r} is not 'true' or 'false'")
    return raw == "true"


def _parse_positive_int(raw: str) -> int:
    value = int(raw)  # raises ValueError on non-numeric input, which is what we want
    if value <= 0:
        raise ValueError(f"{value} is not positive")
    return value


def _validate_enforcement(value: str) -> str:
    if value not in ("warn", "enforce"):
        raise ValueError(f"{value!r} is not 'warn' or 'enforce'")
    return value


def _validate_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{value!r} is not a bool")
    return value


def _validate_positive_int(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{value!r} is not a positive int")
    return value


@dataclass(frozen=True)
class PolicyDef:
    key: str
    default: Any
    env_var: str
    parse: Callable[[str], Any]
    validate: Callable[[Any], Any]


POLICIES: dict[str, PolicyDef] = {
    "guardrail_enforcement": PolicyDef(
        key="guardrail_enforcement",
        default="warn",
        env_var="MULCHD_POLICY_GUARDRAIL_ENFORCEMENT",
        parse=_parse_enforcement,
        validate=_validate_enforcement,
    ),
    "default_page_size": PolicyDef(
        key="default_page_size",
        default=50,
        env_var="MULCHD_POLICY_DEFAULT_PAGE_SIZE",
        parse=_parse_positive_int,
        validate=_validate_positive_int,
    ),
    "strict_domains": PolicyDef(
        key="strict_domains",
        default=False,
        env_var="MULCHD_POLICY_STRICT_DOMAINS",
        parse=_parse_bool,
        validate=_validate_bool,
    ),
}


@dataclass(frozen=True)
class ResolvedPolicy:
    value: Any
    source: Literal["locked", "override", "env-default", "code-default"]


async def resolve_policy(project: Project, key: str) -> ResolvedPolicy:
    """Locked env var -> DB override -> seed env var -> code default.

    A DB override is never deleted by a lock taking precedence over it — it's
    only shadowed while the lock is active, and takes effect again if the lock
    is later removed (or the env var is unset entirely).

    ProjectPolicy.value is stored wrapped in a single-element list (see that
    model's docstring for why) — this function is responsible for unwrapping
    it back to the plain value.
    """
    definition = POLICIES[key]
    raw = _get_env(definition.env_var)

    if raw is not None and raw.startswith("ro:"):
        return ResolvedPolicy(value=definition.parse(raw.removeprefix("ro:")), source="locked")

    row = await ProjectPolicy.get_or_none(project=project, key=key)
    if row is not None:
        # ProjectPolicy.value is an untyped JSONField (see its model docstring);
        # unwrap the single-element-list storage convention back to a plain value.
        row_value = cast(list[Any], row.value)  # pyright: ignore[reportUnknownMemberType]
        return ResolvedPolicy(value=row_value[0], source="override")

    if raw is not None:
        return ResolvedPolicy(value=definition.parse(raw), source="env-default")

    return ResolvedPolicy(value=definition.default, source="code-default")


def validate_env_policies() -> None:
    """Fail loudly at startup on a malformed policy env var, locked or not —
    a security-relevant policy like guardrail_enforcement silently falling
    back to its code default because of a typo'd env var is a worse failure
    mode than crashing on boot."""
    for definition in POLICIES.values():
        raw = _get_env(definition.env_var)
        if raw is None:
            continue
        value = raw.removeprefix("ro:")
        try:
            definition.parse(value)
        except ValueError as e:
            raise ValueError(f"{definition.env_var}={raw!r} is invalid: {e}") from e
