"""
SubscriptionRegistry keys on mcp-session-id, not ServerSession object
identity — mcp v2 mints a fresh session proxy per inbound message even
within one connection, so identity-keyed lookups silently stop matching
the same logical subscriber from one call to the next.
"""

from mulchd.mcp.subscriptions import SubscriptionRegistry


def test_two_proxies_same_session_id_are_one_subscriber():
    registry = SubscriptionRegistry()
    proxy_a = object()
    proxy_b = object()

    registry.register("session-1", proxy_a, "infra")
    # A later message on the same connection presents a different proxy
    # object for the same logical session.
    registry.register("session-1", proxy_b, "infra")

    subs = registry.subscribers_for("infra", exclude="unrelated-session")
    assert list(subs.keys()) == ["session-1"]
    # The most recently registered proxy is the one that would receive
    # a notification — it's still a valid delivery target.
    assert subs["session-1"] is proxy_b


def test_exclude_matches_by_session_id_not_object_identity():
    registry = SubscriptionRegistry()
    proxy_at_subscribe_time = object()
    registry.register("session-1", proxy_at_subscribe_time, "infra")

    # The writer's own session-id is known (e.g. from ctx.request.headers),
    # even though the proxy object handed to the write handler is a
    # different instance than the one captured at subscribe time.
    subs = registry.subscribers_for("infra", exclude="session-1")
    assert subs == {}


def test_different_session_ids_remain_isolated():
    registry = SubscriptionRegistry()
    registry.register("session-1", object(), "infra")
    registry.register("session-2", object(), "infra")

    subs = registry.subscribers_for("infra", exclude="session-1")
    assert list(subs.keys()) == ["session-2"]


def test_unregister_session_removes_from_every_domain():
    registry = SubscriptionRegistry()
    registry.register("session-1", object(), "infra")
    registry.register("session-1", object(), "ops")

    registry.unregister_session("session-1")

    assert registry.subscribers_for("infra", exclude="") == {}
    assert registry.subscribers_for("ops", exclude="") == {}
