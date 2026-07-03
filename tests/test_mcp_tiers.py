import pytest


def test_context_vars_start_as_none():
    from mulchd.mcp.context import _ctx, _global_ctx
    assert _ctx.get() is None
    assert _global_ctx.get() is None


def test_resolved_base_url_derived_from_host_port():
    from mulchd.config import Settings
    s = Settings(secret_key="x", admin_password="x", host="localhost", port=9000)
    assert s.resolved_base_url == "http://localhost:9000"


def test_resolved_base_url_explicit_overrides_derivation():
    from mulchd.config import Settings
    s = Settings(secret_key="x", admin_password="x", base_url="https://mulchd.example.com/")
    assert s.resolved_base_url == "https://mulchd.example.com"


def test_admin_contact_defaults_to_none():
    from mulchd.config import Settings
    s = Settings(secret_key="x", admin_password="x")
    assert s.admin_contact is None
