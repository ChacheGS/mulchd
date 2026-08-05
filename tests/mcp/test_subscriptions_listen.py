"""
subscriptions/listen wiring: gate_subscriptions_listen rejects a listen
request naming a URI outside the caller's own org/project, and _fire_notify
publishes to the shared bus using the qualified, query-param-free URI (not
the query-param-laden one _notify_domain builds for the older
resources/subscribe push path) — a mismatch here would silently drop every
subscriptions/listen notification, since the SDK's event matching is an
exact string comparison against what a client subscribed to.
"""

from types import SimpleNamespace

import pytest

from mcp.shared.exceptions import MCPError
from mulchd.mcp.context import auth_ctx
from mulchd.mcp.tier2 import (
    _fire_notify,
    _subscription_bus,
    gate_subscriptions_listen,
    tier2_server,
)
from tests.mcp.conftest import ctx


def test_gate_is_registered_on_the_server():
    """Pins the append target: tier2_server.middleware.append(...) is a
    post-construction list append, not a constructor kwarg — a future SDK
    change to that shape would silently stop enforcing this check."""
    assert gate_subscriptions_listen in tier2_server.middleware


def _listen_ctx(resource_subscriptions):
    """Minimal ServerRequestContext-shaped stand-in for gate_subscriptions_listen:
    only .method and .params are read on this code path."""
    return SimpleNamespace(
        method="subscriptions/listen",
        params={"notifications": {"resourceSubscriptions": resource_subscriptions}},
    )


async def test_gate_rejects_a_uri_for_a_different_project(team):
    t = team
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    called = False

    async def call_next(_ctx):
        nonlocal called
        called = True
        return SimpleNamespace()

    try:
        with pytest.raises(MCPError):
            await gate_subscriptions_listen(
                _listen_ctx(["mulchd://other-org/other-project/domain/infra"]), call_next
            )
        assert not called
    finally:
        auth_ctx.reset(token)


async def test_gate_accepts_a_uri_for_the_caller_own_project(team):
    t = team
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    called = False

    async def call_next(_ctx):
        nonlocal called
        called = True
        return SimpleNamespace()

    try:
        result = await gate_subscriptions_listen(
            _listen_ctx(["mulchd://acme/infra/domain/infra"]), call_next
        )
        assert called
        assert result is not None
    finally:
        auth_ctx.reset(token)


async def test_gate_rejects_when_no_auth_context():
    called = False

    async def call_next(_ctx):
        nonlocal called
        called = True
        return SimpleNamespace()

    with pytest.raises(MCPError):
        await gate_subscriptions_listen(
            _listen_ctx(["mulchd://acme/infra/domain/infra"]), call_next
        )
    assert not called


async def test_fire_notify_publishes_qualified_uri_to_bus(team, data_path):
    """A listener subscribed via _subscription_bus.subscribe(...) receives the
    event, and the event's uri is exactly the qualified, query-param-free
    form (mulchd://acme/infra/domain/infra) — not _notify_domain's
    query-param-laden variant built for the older resources/subscribe push
    path (mulchd://acme/infra/infra?actor=...). A mismatch here would
    silently drop every subscriptions/listen notification, since the SDK's
    event matching is an exact string comparison."""
    t = team
    received = []

    def listener(event):
        received.append(event)

    unsubscribe = _subscription_bus.subscribe(listener)
    try:
        auth = ctx(t.carlos, t.org, t.infra)
        _fire_notify("infra", auth, "write", {"id": "mx-1", "type": "note", "content": "x"})
        # _fire_notify schedules the publish as a background task; let it run.
        import asyncio

        await asyncio.sleep(0)
        await asyncio.sleep(0)
    finally:
        unsubscribe()

    assert len(received) == 1
    assert received[0].uri == "mulchd://acme/infra/domain/infra"
