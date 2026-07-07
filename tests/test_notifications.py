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

    # Dead session should be removed from registry
    assert dead_session not in fake_registry.subscribers_for("arch", exclude=None)


@pytest.mark.asyncio
async def test_search_records_registers_when_subscribe_true_and_domains_given(
    notify_data_path, monkeypatch, db
):
    """search_records registers domains when subscribe=True and domains is specified."""
    from unittest.mock import MagicMock, AsyncMock
    from mulchd.mcp import tier2 as tier2_module
    from mulchd.mcp.tier2 import _search_expertise
    from mulchd.mcp.subscriptions import SubscriptionRegistry
    from mulchd.auth import AuthContext
    from mulchd.models import Organization, Project, User, Role

    org = await Organization.create(slug="s1", display_name="S")
    project = await Project.create(slug="p1", display_name="P", org=org)
    user = await User.create(username="s1u", display_name="U", token_hash="s1t")
    ctx = AuthContext(user=user, project=project, org=org, role=Role.WRITER)

    fake_registry = SubscriptionRegistry()
    fake_session = object()
    fake_ctx = MagicMock()
    fake_ctx.session = fake_session

    monkeypatch.setattr(tier2_module, "registry", fake_registry)
    monkeypatch.setattr(type(tier2_module.tier2_server), "request_context",
                        property(lambda self: fake_ctx))
    monkeypatch.setattr(tier2_module, "search_domains", AsyncMock(return_value=[]))
    monkeypatch.setattr(tier2_module, "list_available_domains", AsyncMock(return_value=[{"name": "arch"}]))

    await _search_expertise({"query": "anything", "domains": ["arch"], "subscribe": True}, ctx)

    assert fake_session in fake_registry.subscribers_for("arch", exclude=None)


@pytest.mark.asyncio
async def test_search_records_skips_register_when_subscribe_false(
    notify_data_path, monkeypatch, db
):
    """search_records does not register when subscribe=False."""
    from unittest.mock import MagicMock, AsyncMock
    from mulchd.mcp import tier2 as tier2_module
    from mulchd.mcp.tier2 import _search_expertise
    from mulchd.mcp.subscriptions import SubscriptionRegistry
    from mulchd.auth import AuthContext
    from mulchd.models import Organization, Project, User, Role

    org = await Organization.create(slug="s2", display_name="S")
    project = await Project.create(slug="p2", display_name="P", org=org)
    user = await User.create(username="s2u", display_name="U", token_hash="s2t")
    ctx = AuthContext(user=user, project=project, org=org, role=Role.WRITER)

    fake_registry = SubscriptionRegistry()
    fake_session = object()

    monkeypatch.setattr(tier2_module, "registry", fake_registry)
    monkeypatch.setattr(tier2_module, "search_domains", AsyncMock(return_value=[]))
    monkeypatch.setattr(tier2_module, "list_available_domains", AsyncMock(return_value=[{"name": "arch"}]))

    await _search_expertise({"query": "anything", "domains": ["arch"], "subscribe": False}, ctx)

    assert fake_session not in fake_registry.subscribers_for("arch", exclude=None)


@pytest.mark.asyncio
async def test_search_records_skips_register_when_no_domains(
    notify_data_path, monkeypatch, db
):
    """search_records does not register when domains is not specified (search-all)."""
    from unittest.mock import MagicMock, AsyncMock
    from mulchd.mcp import tier2 as tier2_module
    from mulchd.mcp.tier2 import _search_expertise
    from mulchd.mcp.subscriptions import SubscriptionRegistry
    from mulchd.auth import AuthContext
    from mulchd.models import Organization, Project, User, Role

    org = await Organization.create(slug="s3", display_name="S")
    project = await Project.create(slug="p3", display_name="P", org=org)
    user = await User.create(username="s3u", display_name="U", token_hash="s3t")
    ctx = AuthContext(user=user, project=project, org=org, role=Role.WRITER)

    fake_registry = SubscriptionRegistry()
    fake_session = object()
    monkeypatch.setattr(tier2_module, "registry", fake_registry)
    monkeypatch.setattr(tier2_module, "search_domains", AsyncMock(return_value=[]))
    monkeypatch.setattr(tier2_module, "list_available_domains", AsyncMock(return_value=[]))

    await _search_expertise({"query": "anything", "subscribe": True}, ctx)

    # No domains specified → should not register anything
    assert fake_session not in fake_registry.subscribers_for("arch", exclude=None)


@pytest.mark.asyncio
async def test_write_record_registers_and_dispatches_notify(notify_data_path, monkeypatch, db):
    """_record_expertise registers session and fires _notify_domain when subscribe=True."""
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

    fake_registry = SubscriptionRegistry()
    fake_session = object()
    fake_ctx = MagicMock()
    fake_ctx.session = fake_session

    dispatched = []

    monkeypatch.setattr(tier2_module, "registry", fake_registry)
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
        "subscribe": True,
    }, ctx)

    assert fake_session in fake_registry.subscribers_for("conventions", exclude=None)
    assert any("_notify_domain" in d for d in dispatched)


@pytest.mark.asyncio
async def test_edit_record_registers_when_subscribe_true(notify_data_path, monkeypatch, db):
    """_edit_record registers session and dispatches _notify_domain when subscribe=True."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from mulchd.mcp import tier2 as tier2_module
    from mulchd.mcp.subscriptions import SubscriptionRegistry
    from mulchd.auth import AuthContext
    from mulchd.models import Organization, Project, User, Role

    org = await Organization.create(slug="e1", display_name="E")
    project = await Project.create(slug="e1p", display_name="E", org=org)
    user = await User.create(username="e1u", display_name="Editor", token_hash="e1t")

    ctx = AuthContext(user=user, project=project, org=org, role=Role.WRITER)

    fake_registry = SubscriptionRegistry()
    fake_session = object()
    fake_ctx = MagicMock()
    fake_ctx.session = fake_session

    dispatched = []

    monkeypatch.setattr(tier2_module, "registry", fake_registry)
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
        "subscribe": True,
    }, ctx)

    assert fake_session in fake_registry.subscribers_for("conventions", exclude=None)
    assert any("_notify_domain" in d for d in dispatched)


@pytest.mark.asyncio
async def test_delete_record_registers_when_subscribe_true(notify_data_path, monkeypatch, db):
    """_delete_record registers session and dispatches _notify_domain when subscribe=True."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from mulchd.mcp import tier2 as tier2_module
    from mulchd.mcp.subscriptions import SubscriptionRegistry
    from mulchd.auth import AuthContext
    from mulchd.models import Organization, Project, User, Role

    org = await Organization.create(slug="d1", display_name="D")
    project = await Project.create(slug="d1p", display_name="D", org=org)
    user = await User.create(username="d1u", display_name="Deleter", token_hash="d1t")

    ctx = AuthContext(user=user, project=project, org=org, role=Role.WRITER)

    fake_registry = SubscriptionRegistry()
    fake_session = object()
    fake_ctx = MagicMock()
    fake_ctx.session = fake_session

    dispatched = []

    monkeypatch.setattr(tier2_module, "registry", fake_registry)
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
        "subscribe": True,
    }, ctx)

    assert fake_session in fake_registry.subscribers_for("conventions", exclude=None)
    assert any("_notify_domain" in d for d in dispatched)
