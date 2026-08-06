"""
Policy registry and resolution tests.
"""

import pytest

from mulchd.models import Organization, Project
from mulchd.policies import (
    POLICIES,
    ResolvedPolicy,
    resolve_policy,
    validate_env_policies,
)


@pytest.fixture
async def project(db):
    org = await Organization.create(slug="acme", display_name="Acme")
    return await Project.create(slug="infra", display_name="Infra", org=org)


async def test_resolve_policy_code_default_when_nothing_set(project, monkeypatch):
    for definition in POLICIES.values():
        monkeypatch.delenv(definition.env_var, raising=False)

    resolved = await resolve_policy(project, "guardrail_enforcement")
    assert resolved == ResolvedPolicy(value="warn", source="code-default")


async def test_resolve_policy_env_default_when_no_override(project, monkeypatch):
    monkeypatch.setenv("MULCHD_POLICY_GUARDRAIL_ENFORCEMENT", "enforce")

    resolved = await resolve_policy(project, "guardrail_enforcement")
    assert resolved == ResolvedPolicy(value="enforce", source="env-default")


async def test_resolve_policy_db_override_wins_over_env_default(project, monkeypatch):
    from mulchd.models import ProjectPolicy

    monkeypatch.setenv("MULCHD_POLICY_GUARDRAIL_ENFORCEMENT", "enforce")
    await ProjectPolicy.create(project=project, key="guardrail_enforcement", value=["warn"])

    resolved = await resolve_policy(project, "guardrail_enforcement")
    assert resolved == ResolvedPolicy(value="warn", source="override")


async def test_resolve_policy_locked_env_var_wins_over_db_override(project, monkeypatch):
    from mulchd.models import ProjectPolicy

    monkeypatch.setenv("MULCHD_POLICY_GUARDRAIL_ENFORCEMENT", "ro:enforce")
    await ProjectPolicy.create(project=project, key="guardrail_enforcement", value=["warn"])

    resolved = await resolve_policy(project, "guardrail_enforcement")
    assert resolved == ResolvedPolicy(value="enforce", source="locked")


async def test_resolve_policy_override_survives_lock_removal(project, monkeypatch):
    """A DB override isn't deleted when shadowed by a lock — it takes effect
    again once the lock is removed."""
    from mulchd.models import ProjectPolicy

    monkeypatch.setenv("MULCHD_POLICY_GUARDRAIL_ENFORCEMENT", "ro:enforce")
    await ProjectPolicy.create(project=project, key="guardrail_enforcement", value=["warn"])
    assert (await resolve_policy(project, "guardrail_enforcement")).source == "locked"

    monkeypatch.setenv("MULCHD_POLICY_GUARDRAIL_ENFORCEMENT", "enforce")  # lock removed
    resolved = await resolve_policy(project, "guardrail_enforcement")
    assert resolved == ResolvedPolicy(value="warn", source="override")


async def test_resolve_policy_default_page_size(project, monkeypatch):
    monkeypatch.delenv("MULCHD_POLICY_DEFAULT_PAGE_SIZE", raising=False)
    assert (await resolve_policy(project, "default_page_size")).value == 50

    monkeypatch.setenv("MULCHD_POLICY_DEFAULT_PAGE_SIZE", "10")
    assert (await resolve_policy(project, "default_page_size")).value == 10


async def test_resolve_policy_strict_domains(project, monkeypatch):
    monkeypatch.delenv("MULCHD_POLICY_STRICT_DOMAINS", raising=False)
    assert (await resolve_policy(project, "strict_domains")).value is False

    monkeypatch.setenv("MULCHD_POLICY_STRICT_DOMAINS", "true")
    assert (await resolve_policy(project, "strict_domains")).value is True


def test_every_policy_default_round_trips_its_own_validator():
    for definition in POLICIES.values():
        assert definition.validate(definition.default) == definition.default


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        ("guardrail_enforcement", "enforce", "enforce"),
        ("guardrail_enforcement", "ro:enforce", "enforce"),
        ("default_page_size", "25", 25),
        ("default_page_size", "ro:25", 25),
        ("strict_domains", "true", True),
        ("strict_domains", "ro:true", True),
    ],
)
def test_ro_prefix_parses_identically_to_unprefixed(key, raw, expected):
    definition = POLICIES[key]
    stripped = raw.removeprefix("ro:")
    assert definition.parse(stripped) == expected


def test_validate_env_policies_raises_on_malformed_value(monkeypatch):
    monkeypatch.setenv("MULCHD_POLICY_DEFAULT_PAGE_SIZE", "notanumber")
    with pytest.raises(ValueError, match="MULCHD_POLICY_DEFAULT_PAGE_SIZE"):
        validate_env_policies()


def test_validate_env_policies_raises_on_invalid_enforcement_value(monkeypatch):
    monkeypatch.setenv("MULCHD_POLICY_GUARDRAIL_ENFORCEMENT", "sometimes")
    with pytest.raises(ValueError, match="MULCHD_POLICY_GUARDRAIL_ENFORCEMENT"):
        validate_env_policies()


def test_validate_env_policies_passes_with_nothing_set(monkeypatch):
    for definition in POLICIES.values():
        monkeypatch.delenv(definition.env_var, raising=False)
    validate_env_policies()  # must not raise


def test_validate_env_policies_accepts_locked_values(monkeypatch):
    monkeypatch.setenv("MULCHD_POLICY_STRICT_DOMAINS", "ro:true")
    validate_env_policies()  # must not raise


async def test_resolve_policy_reads_dotenv_fallback(project, monkeypatch, tmp_path):
    """A policy env var set only in .env (not the real process environment)
    still resolves — matching how Settings itself sources MULCHD_* values."""
    monkeypatch.delenv("MULCHD_POLICY_STRICT_DOMAINS", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("MULCHD_POLICY_STRICT_DOMAINS=true\n")

    resolved = await resolve_policy(project, "strict_domains")
    assert resolved == ResolvedPolicy(value=True, source="env-default")


async def test_resolve_policy_real_env_var_wins_over_dotenv(project, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("MULCHD_POLICY_STRICT_DOMAINS=true\n")
    monkeypatch.setenv("MULCHD_POLICY_STRICT_DOMAINS", "false")

    resolved = await resolve_policy(project, "strict_domains")
    assert resolved == ResolvedPolicy(value=False, source="env-default")
