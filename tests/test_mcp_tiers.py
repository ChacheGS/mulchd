import pytest


def test_context_vars_start_as_none():
    from mulchd.mcp.context import _ctx, _global_ctx
    assert _ctx.get() is None
    assert _global_ctx.get() is None
