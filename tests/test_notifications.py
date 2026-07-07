# tests/test_notifications.py
import pytest
from mulchd.mcp.subscriptions import SubscriptionRegistry


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
