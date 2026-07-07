# tests/test_notifications.py
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from mulchd.mcp import tier2 as tier2_module
from mulchd.mcp.subscriptions import SubscriptionRegistry


@pytest.fixture
def notify_data_path(tmp_path, monkeypatch):
    from mulchd.config import settings
    monkeypatch.setattr(settings, "data_path", tmp_path)
    return tmp_path


def _session(name: str):
    """Cheap mock — identity comparison is all we need."""
    return object()


def test_register_and_lookup():
    r = SubscriptionRegistry()
    s1, s2 = _session("a"), _session("b")
    r.register(s1, "arch")
    r.register(s2, "arch")
    assert r.subscribers_for("arch", exclude=s1) == {s2}
    assert r.subscribers_for("arch", exclude=s2) == {s1}


def test_exclude_self_only():
    r = SubscriptionRegistry()
    s = _session("a")
    r.register(s, "arch")
    assert r.subscribers_for("arch", exclude=s) == set()


def test_empty_domain_returns_empty_set():
    r = SubscriptionRegistry()
    assert r.subscribers_for("nonexistent", exclude=None) == set()


def test_unregister_removes_from_all_domains():
    r = SubscriptionRegistry()
    s = _session("a")
    r.register(s, "arch")
    r.register(s, "conventions")
    r.unregister_session(s)
    assert r.subscribers_for("arch", exclude=None) == set()
    assert r.subscribers_for("conventions", exclude=None) == set()


def test_multiple_domains_independent():
    r = SubscriptionRegistry()
    s1, s2 = _session("a"), _session("b")
    r.register(s1, "arch")
    r.register(s2, "conventions")
    assert r.subscribers_for("arch", exclude=None) == {s1}
    assert r.subscribers_for("conventions", exclude=None) == {s2}


@pytest.mark.asyncio
async def test_read_records_registers_when_subscribe_true(notify_data_path, db, monkeypatch):
    """_read_expertise registers the session for each domain when subscribe=True."""
    from mulchd.auth import AuthContext
    from mulchd.models import Organization, Project, User, Role

    org = await Organization.create(slug="o", display_name="O")
    project = await Project.create(slug="p", display_name="P", org=org)
    user = await User.create(username="u", display_name="U", token_hash="x")

    ctx = AuthContext(user=user, project=project, org=org, role=Role.WRITER)

    # Seed an empty domain JSONL so _read_expertise doesn't fail on missing file
    expertise = notify_data_path / "o" / "p" / ".mulch" / "expertise"
    expertise.mkdir(parents=True, exist_ok=True)
    (expertise / "arch.jsonl").write_text("")

    fake_registry = SubscriptionRegistry()
    fake_session = object()
    fake_ctx = MagicMock()
    fake_ctx.session = fake_session

    monkeypatch.setattr(tier2_module, "registry", fake_registry)
    monkeypatch.setattr(
        type(tier2_module.tier2_server),
        "request_context",
        property(lambda self: fake_ctx),
    )

    from mulchd.mcp.tier2 import _read_expertise
    await _read_expertise({"domains": ["arch"], "subscribe": True}, ctx)

    assert fake_session in fake_registry.subscribers_for("arch", exclude=None)


@pytest.mark.asyncio
async def test_read_records_skips_register_when_subscribe_false(notify_data_path, db, monkeypatch):
    from mulchd.auth import AuthContext
    from mulchd.models import Organization, Project, User, Role

    org = await Organization.create(slug="o2", display_name="O")
    project = await Project.create(slug="p2", display_name="P", org=org)
    user = await User.create(username="u2", display_name="U", token_hash="y")

    ctx = AuthContext(user=user, project=project, org=org, role=Role.WRITER)

    expertise = notify_data_path / "o2" / "p2" / ".mulch" / "expertise"
    expertise.mkdir(parents=True, exist_ok=True)
    (expertise / "arch.jsonl").write_text("")

    fake_registry = SubscriptionRegistry()
    fake_session = object()
    fake_ctx = MagicMock()
    fake_ctx.session = fake_session

    monkeypatch.setattr(tier2_module, "registry", fake_registry)
    # subscribe=False: no need to mock request_context at all

    from mulchd.mcp.tier2 import _read_expertise
    await _read_expertise({"domains": ["arch"], "subscribe": False}, ctx)

    assert fake_session not in fake_registry.subscribers_for("arch", exclude=None)
