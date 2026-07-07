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


def test_unregister_domain_specific():
    r = SubscriptionRegistry()
    s = _session("a")
    r.register(s, "arch")
    r.register(s, "conventions")
    r.unregister(s, "arch")
    assert r.subscribers_for("arch", exclude=None) == set()
    assert r.subscribers_for("conventions", exclude=None) == {s}


@pytest.mark.asyncio
async def test_notify_domain_sends_to_subscribers(monkeypatch, db):
    """_notify_domain fans out send_resource_updated to all subscribers except the actor."""
    from unittest.mock import AsyncMock, MagicMock
    from mulchd.mcp import tier2 as tier2_module
    from mulchd.mcp.tier2 import _notify_domain
    from mulchd.mcp.subscriptions import SubscriptionRegistry

    fake_registry = SubscriptionRegistry()
    subscriber = MagicMock()
    subscriber.send_resource_updated = AsyncMock()
    actor_session = object()
    fake_registry.register(subscriber, "arch")

    monkeypatch.setattr(tier2_module, "registry", fake_registry)

    ctx = MagicMock()
    ctx.user.display_name = "Alice"
    ctx.org.slug = "myorg"
    ctx.project.slug = "myproj"

    record = {
        "type": "decision",
        "classification": "foundational",
        "title": "Always validate at the boundary",
        "recorded_at": "2026-07-07T10:00:00Z",
    }
    await _notify_domain("arch", actor_session, ctx, "write", record)

    subscriber.send_resource_updated.assert_called_once()
    called_uri = str(subscriber.send_resource_updated.call_args[0][0])
    assert "arch" in called_uri
    assert "actor=Alice" in called_uri
    assert "action=write" in called_uri


@pytest.mark.asyncio
async def test_notify_domain_skips_actor_session(monkeypatch, db):
    """Actor does not receive their own notification."""
    from unittest.mock import AsyncMock, MagicMock
    from mulchd.mcp import tier2 as tier2_module
    from mulchd.mcp.tier2 import _notify_domain
    from mulchd.mcp.subscriptions import SubscriptionRegistry

    fake_registry = SubscriptionRegistry()
    actor_session = MagicMock()
    actor_session.send_resource_updated = AsyncMock()
    fake_registry.register(actor_session, "arch")

    monkeypatch.setattr(tier2_module, "registry", fake_registry)

    ctx = MagicMock()
    ctx.user.display_name = "Bob"
    ctx.org.slug = "o"
    ctx.project.slug = "p"

    record = {"type": "convention", "classification": "tactical", "content": "x"}
    await _notify_domain("arch", actor_session, ctx, "write", record)

    actor_session.send_resource_updated.assert_not_called()


@pytest.mark.asyncio
async def test_notify_domain_cleans_up_dead_sessions(monkeypatch, db):
    """Sessions that raise on send_resource_updated are unregistered."""
    from unittest.mock import AsyncMock, MagicMock
    from mulchd.mcp import tier2 as tier2_module
    from mulchd.mcp.tier2 import _notify_domain
    from mulchd.mcp.subscriptions import SubscriptionRegistry

    fake_registry = SubscriptionRegistry()
    dead_session = MagicMock()
    dead_session.send_resource_updated = AsyncMock(side_effect=Exception("connection closed"))
    actor_session = object()
    fake_registry.register(dead_session, "arch")

    monkeypatch.setattr(tier2_module, "registry", fake_registry)

    ctx = MagicMock()
    ctx.user.display_name = "Carol"
    ctx.org.slug = "o"
    ctx.project.slug = "p"

    record = {"type": "pattern", "classification": "observational", "name": "foo"}
    await _notify_domain("arch", actor_session, ctx, "write", record)

    assert dead_session not in fake_registry.subscribers_for("arch", exclude=None)


@pytest.mark.asyncio
async def test_write_record_dispatches_notify(notify_data_path, monkeypatch, db):
    """_record_expertise fires _notify_domain on write."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from mulchd.mcp import tier2 as tier2_module
    from mulchd.mcp.subscriptions import SubscriptionRegistry
    from mulchd.auth import AuthContext
    from mulchd.models import Organization, Project, User, Role

    org = await Organization.create(slug="w1", display_name="W")
    project = await Project.create(slug="w1p", display_name="W", org=org)
    user = await User.create(username="w1u", display_name="Writer", token_hash="w1t")

    ctx = AuthContext(user=user, project=project, org=org, role=Role.WRITER)

    fake_ctx = MagicMock()
    fake_ctx.session = object()

    dispatched = []

    monkeypatch.setattr(type(tier2_module.tier2_server), "request_context",
                        property(lambda self: fake_ctx))
    monkeypatch.setattr(tier2_module, "write_record",
                        AsyncMock(return_value={"id": "mx-w1", "type": "convention",
                                                "classification": "tactical",
                                                "content": "x", "recorded_at": "2026-07-07T00:00:00Z"}))
    monkeypatch.setattr(tier2_module, "init_ml_project", AsyncMock())
    monkeypatch.setattr(tier2_module, "_get_or_create_session", MagicMock(return_value="s1"))
    monkeypatch.setattr(tier2_module, "_supersede_alerts", AsyncMock(return_value={}))
    monkeypatch.setattr("mulchd.models.RecordMeta.create", AsyncMock())
    monkeypatch.setattr("mulchd.models.RecordEvent.create", AsyncMock())

    original_create_task = asyncio.create_task
    def capture_create_task(coro, **kwargs):
        dispatched.append(coro.__qualname__ if hasattr(coro, "__qualname__") else str(coro))
        return original_create_task(coro, **kwargs)
    monkeypatch.setattr(asyncio, "create_task", capture_create_task)

    from mulchd.mcp.tier2 import _record_expertise
    await _record_expertise({
        "domain": "conventions",
        "type": "convention",
        "classification": "tactical",
        "content": "Always validate at boundaries",
    }, ctx)

    assert any("_notify_domain" in d for d in dispatched)


@pytest.mark.asyncio
async def test_edit_record_dispatches_notify(notify_data_path, monkeypatch, db):
    """_edit_record dispatches _notify_domain."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from mulchd.mcp import tier2 as tier2_module
    from mulchd.auth import AuthContext
    from mulchd.models import Organization, Project, User, Role

    org = await Organization.create(slug="e1", display_name="E")
    project = await Project.create(slug="e1p", display_name="E", org=org)
    user = await User.create(username="e1u", display_name="Editor", token_hash="e1t")

    ctx = AuthContext(user=user, project=project, org=org, role=Role.WRITER)

    fake_ctx = MagicMock()
    fake_ctx.session = object()

    dispatched = []

    monkeypatch.setattr(type(tier2_module.tier2_server), "request_context",
                        property(lambda self: fake_ctx))
    monkeypatch.setattr(tier2_module, "find_record",
                        AsyncMock(return_value={"type": "convention", "classification": "tactical",
                                                "content": "old content", "owner": "e1u"}))
    monkeypatch.setattr(tier2_module, "edit_record", AsyncMock())
    monkeypatch.setattr(tier2_module, "_get_or_create_session", MagicMock(return_value="s2"))
    monkeypatch.setattr("mulchd.models.RecordEvent.create", AsyncMock())
    monkeypatch.setattr("mulchd.models.RecordEdit.create", AsyncMock())

    original_create_task = asyncio.create_task
    def capture_create_task(coro, **kwargs):
        dispatched.append(coro.__qualname__ if hasattr(coro, "__qualname__") else str(coro))
        return original_create_task(coro, **kwargs)
    monkeypatch.setattr(asyncio, "create_task", capture_create_task)

    from mulchd.mcp.tier2 import _edit_record
    await _edit_record({
        "record_id": "mx-e1",
        "domain": "conventions",
        "content": "new content",
    }, ctx)

    assert any("_notify_domain" in d for d in dispatched)


@pytest.mark.asyncio
async def test_delete_record_dispatches_notify(notify_data_path, monkeypatch, db):
    """_delete_record dispatches _notify_domain."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from mulchd.mcp import tier2 as tier2_module
    from mulchd.auth import AuthContext
    from mulchd.models import Organization, Project, User, Role

    org = await Organization.create(slug="d1", display_name="D")
    project = await Project.create(slug="d1p", display_name="D", org=org)
    user = await User.create(username="d1u", display_name="Deleter", token_hash="d1t")

    ctx = AuthContext(user=user, project=project, org=org, role=Role.WRITER)

    fake_ctx = MagicMock()
    fake_ctx.session = object()

    dispatched = []

    monkeypatch.setattr(type(tier2_module.tier2_server), "request_context",
                        property(lambda self: fake_ctx))
    monkeypatch.setattr(tier2_module, "find_record",
                        AsyncMock(return_value={"type": "convention", "classification": "tactical",
                                                "content": "doomed record", "owner": "d1u"}))
    monkeypatch.setattr(tier2_module, "delete_record", AsyncMock())
    monkeypatch.setattr(tier2_module, "_get_or_create_session", MagicMock(return_value="s3"))
    monkeypatch.setattr(tier2_module, "read_domain_records",
                        AsyncMock(return_value=[{"content": "other stuff"}]))
    monkeypatch.setattr("mulchd.models.RecordEvent.create", AsyncMock())

    original_create_task = asyncio.create_task
    def capture_create_task(coro, **kwargs):
        dispatched.append(coro.__qualname__ if hasattr(coro, "__qualname__") else str(coro))
        return original_create_task(coro, **kwargs)
    monkeypatch.setattr(asyncio, "create_task", capture_create_task)

    from mulchd.mcp.tier2 import _delete_record
    await _delete_record({
        "record_id": "mx-d1",
        "domain": "conventions",
    }, ctx)

    assert any("_notify_domain" in d for d in dispatched)
