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
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
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


@lru_cache(maxsize=8)
def _cached_dotenv_values(resolved_path: str) -> dict[str, str | None]:
    """The .env file can only change on process restart — there's no
    live-reload anywhere in this app — so parse it once per real file, for
    the process's lifetime, instead of re-parsing on every call.

    Keyed by resolved absolute path (not a bare "compute once, ever" cache,
    and not keyed by the literal ".env" string) so that tests which
    monkeypatch.chdir into a fresh tmp_path and write their own .env each get
    an independent cache entry instead of reusing another test's content.
    """
    return dotenv_values(resolved_path)


def _get_env(name: str) -> str | None:
    """Real process env wins over .env, matching pydantic-settings' own
    documented precedence — .env is a fallback for values that were never
    exported into the environment at all."""
    value = os.environ.get(name)
    if value is not None:
        return value
    resolved_path = str(Path(_DOTENV_PATH).resolve())
    return _cached_dotenv_values(resolved_path).get(name)


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
    # Explicit, declared value shape — NOT inferred from type(default) by any
    # caller. In Python, bool is a subtype of int (isinstance(True, int) is
    # True), so any code that tried to infer "is this a bool policy or an int
    # policy" from the runtime type of `default` would need to check bool
    # before int, and that ordering requirement would be invisible and easy
    # to silently break (e.g. by reordering template conditionals). Callers
    # that need to pick a control/type by kind (e.g. the admin UI template)
    # must branch on this field, not on `default`'s runtime type.
    kind: Literal["bool", "int", "str"]


POLICIES: dict[str, PolicyDef] = {
    "guardrail_enforcement": PolicyDef(
        key="guardrail_enforcement",
        default="warn",
        env_var="MULCHD_POLICY_GUARDRAIL_ENFORCEMENT",
        parse=_parse_enforcement,
        validate=_validate_enforcement,
        kind="str",
    ),
    "default_page_size": PolicyDef(
        key="default_page_size",
        default=50,
        env_var="MULCHD_POLICY_DEFAULT_PAGE_SIZE",
        parse=_parse_positive_int,
        validate=_validate_positive_int,
        kind="int",
    ),
    "strict_domains": PolicyDef(
        key="strict_domains",
        default=False,
        env_var="MULCHD_POLICY_STRICT_DOMAINS",
        parse=_parse_bool,
        validate=_validate_bool,
        kind="bool",
    ),
}


@dataclass(frozen=True)
class ResolvedPolicy:
    value: Any
    source: Literal["locked", "override", "env-default", "code-default"]


# Unlike the .env cache above, a DB override can genuinely change at runtime
# (an admin edits it via the admin UI in a later task), so this is a short
# TTL cache rather than a permanent one — a few seconds of staleness is an
# acceptable tradeoff for a policy value, not a security-critical setting.
_OVERRIDE_CACHE_TTL_SECONDS = 5.0
_override_cache: dict[tuple[int, str], tuple[Any, float]] = {}


def _clear_policy_cache() -> None:  # pyright: ignore[reportUnusedFunction]
    """Test-only escape hatch — clears the DB-override TTL cache so tests
    don't see a stale cached value (or a stale cache miss) left over from an
    earlier test reusing the same (project.id, key) pair. (Called from
    tests/test_policies.py, which pyright doesn't cross-reference here.)"""
    _override_cache.clear()


def invalidate_policy_override(project: Project, key: str) -> None:
    """Drop the cached override for one (project, key) pair immediately.

    The admin UI's write path (see admin/projects.py's set_project_policy)
    must call this right after writing a ProjectPolicy row — otherwise the
    TTL cache can still be holding a pre-write miss cached from the same
    request's earlier resolve_policy lock-check call, and the PRG redirect
    right after the write would render the stale (pre-write) value for up to
    _OVERRIDE_CACHE_TTL_SECONDS. The TTL alone is only sufficient for
    incidental cross-admin staleness, not for a write immediately followed by
    a read of the thing just written.
    """
    _override_cache.pop((project.id, key), None)


class _NoOverride:
    """Sentinel distinguishing "no DB override row exists" from an override
    whose unwrapped value happens to be None — a cached miss is still a
    valid, cacheable fact, not the absence of a cache entry."""


_NO_OVERRIDE = _NoOverride()


async def _get_cached_override(project: Project, key: str) -> Any:
    """TTL-cached lookup of a ProjectPolicy override's unwrapped value.
    Returns _NO_OVERRIDE if no override row exists (also cached, so repeated
    no-override calls skip the DB too)."""
    cache_key = (project.id, key)
    cached = _override_cache.get(cache_key)
    if cached is not None:
        value, cached_at = cached
        if time.monotonic() - cached_at < _OVERRIDE_CACHE_TTL_SECONDS:
            return value

    row = await ProjectPolicy.get_or_none(project=project, key=key)
    if row is not None:
        # ProjectPolicy.value is an untyped JSONField (see its model docstring);
        # unwrap the single-element-list storage convention back to a plain value.
        row_value = cast(list[Any], row.value)  # pyright: ignore[reportUnknownMemberType]
        value = row_value[0]
    else:
        value = _NO_OVERRIDE

    _override_cache[cache_key] = (value, time.monotonic())
    return value


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

    override_value = await _get_cached_override(project, key)
    if override_value is not _NO_OVERRIDE:
        return ResolvedPolicy(value=override_value, source="override")

    if raw is not None:
        return ResolvedPolicy(value=definition.parse(raw), source="env-default")

    return ResolvedPolicy(value=definition.default, source="code-default")


def resolve_global_default(key: str) -> Any:
    """Env var or code default for a policy, skipping the per-project
    DB-override/lock resolution that resolve_policy does. For admin-UI
    surfaces that aren't scoped to a single project (e.g. pagination on
    cross-project lists like Orgs/Users), there's no Project to resolve a
    per-project override against — but the env var and code default still
    apply globally, so this reuses that part of the same policy definition
    instead of hardcoding a second, unrelated constant."""
    definition = POLICIES[key]
    raw = _get_env(definition.env_var)
    if raw is None:
        return definition.default
    return definition.parse(raw.removeprefix("ro:") if raw.startswith("ro:") else raw)


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
