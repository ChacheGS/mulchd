"""
SubscriptionRegistry keys on (org, project, domain) and mcp-session-id, not
bare domain name or ServerSession object identity — two independent fixes:
mcp v2 mints a fresh session proxy per inbound message even within one
connection, so identity-keyed lookups silently stop matching the same
logical subscriber from one call to the next; and a bare domain name is not
unique across projects, so two projects with a same-named domain would
otherwise cross-notify each other.
"""

from mulchd.mcp.subscriptions import SubscriptionRegistry


def test_two_proxies_same_session_id_are_one_subscriber():
    registry = SubscriptionRegistry()
    proxy_a = object()
    proxy_b = object()

    registry.register("session-1", proxy_a, "acme", "infra", "infra")
    # A later message on the same connection presents a different proxy
    # object for the same logical session.
    registry.register("session-1", proxy_b, "acme", "infra", "infra")

    subs = registry.subscribers_for("acme", "infra", "infra", exclude="unrelated-session")
    assert list(subs.keys()) == ["session-1"]
    # The most recently registered proxy is the one that would receive
    # a notification — it's still a valid delivery target.
    assert subs["session-1"] is proxy_b


def test_exclude_matches_by_session_id_not_object_identity():
    registry = SubscriptionRegistry()
    proxy_at_subscribe_time = object()
    registry.register("session-1", proxy_at_subscribe_time, "acme", "infra", "infra")

    # The writer's own session-id is known (e.g. from ctx.request.headers),
    # even though the proxy object handed to the write handler is a
    # different instance than the one captured at subscribe time.
    subs = registry.subscribers_for("acme", "infra", "infra", exclude="session-1")
    assert subs == {}


def test_different_session_ids_remain_isolated():
    registry = SubscriptionRegistry()
    registry.register("session-1", object(), "acme", "infra", "infra")
    registry.register("session-2", object(), "acme", "infra", "infra")

    subs = registry.subscribers_for("acme", "infra", "infra", exclude="session-1")
    assert list(subs.keys()) == ["session-2"]


def test_unregister_session_removes_from_every_domain():
    registry = SubscriptionRegistry()
    registry.register("session-1", object(), "acme", "infra", "infra")
    registry.register("session-1", object(), "acme", "infra", "ops")

    registry.unregister_session("session-1")

    assert registry.subscribers_for("acme", "infra", "infra", exclude="") == {}
    assert registry.subscribers_for("acme", "infra", "ops", exclude="") == {}


def test_same_domain_name_different_projects_stay_isolated():
    """Two projects both naming a domain "infra" must not cross-notify —
    the fix this whole file's re-keying exists for."""
    registry = SubscriptionRegistry()
    registry.register("session-acme", object(), "acme", "infra", "infra")
    registry.register("session-other", object(), "other-org", "other-project", "infra")

    acme_subs = registry.subscribers_for("acme", "infra", "infra", exclude="")
    other_subs = registry.subscribers_for("other-org", "other-project", "infra", exclude="")

    assert list(acme_subs.keys()) == ["session-acme"]
    assert list(other_subs.keys()) == ["session-other"]
