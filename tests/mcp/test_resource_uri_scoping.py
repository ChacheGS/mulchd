"""
read_resource/subscribe_resource/unsubscribe_resource reject a URI whose
embedded org/project doesn't match the caller's own auth context — a URI
naming one project's domain must never silently resolve against a different
project's data (or subscription registry entry) because the parser ignored
the org/project segment.
"""

from types import SimpleNamespace

import pytest
from mcp.shared.exceptions import MCPError

from mulchd.mcp.context import auth_ctx
from mulchd.mcp.tier2 import read_resource, subscribe_resource, unsubscribe_resource
from tests.mcp.conftest import ctx


async def test_read_resource_rejects_uri_for_a_different_project(team, data_path):
    from mcp.types import ReadResourceRequestParams

    t = team
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        with pytest.raises(MCPError, match="Unknown resource URI"):
            await read_resource(
                None, ReadResourceRequestParams(uri="mulchd://other-org/other-project/domain/infra")
            )
    finally:
        auth_ctx.reset(token)


async def test_read_resource_rejects_missing_auth_context_as_mcp_error(data_path):
    """A plain ValueError here would get caught by the SDK's generic
    handler-exception path, logged with a full traceback (logger.exception)
    on every occurrence — an expected, client-caused condition shouldn't be
    that noisy. MCPError skips that path and carries its own error code."""
    from mcp.types import ReadResourceRequestParams

    with pytest.raises(MCPError, match="No auth context"):
        await read_resource(None, ReadResourceRequestParams(uri="mulchd://acme/infra/domain/infra"))


async def test_subscribe_resource_ignores_uri_for_a_different_project(team, data_path):
    """subscribe_resource silently no-ops on a mismatched URI (matching the
    existing behavior for an unrecognized URI shape — resources/subscribe has
    no error path, per the spec, only silent non-registration). Uses a real
    fake_ctx (not None) so this actually exercises the org/project check —
    with ctx=None, registration would never happen regardless of that check,
    since the session-id lookup itself would crash first.

    Checks the caller's OWN (acme/infra) bucket, not other-org/other-project:
    subscribe_resource always registers under the authenticated caller's real
    org/project (auth.org.slug/auth.project.slug), never anything derived
    from the URI, so a mismatched URI's own org/project bucket would stay
    empty regardless of whether the check works — that's not the signal that
    the check actually ran. What proves the check ran is that the caller's
    own bucket, which a broken check would populate, stays empty too."""
    from mcp.types import SubscribeRequestParams
    from mulchd.mcp.subscriptions import registry

    fake_ctx = SimpleNamespace(
        request=SimpleNamespace(headers={"mcp-session-id": "test-session"}),
        session=object(),
    )

    t = team
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        await subscribe_resource(
            fake_ctx, SubscribeRequestParams(uri="mulchd://other-org/other-project/domain/infra")
        )
        subs = registry.subscribers_for("acme", "infra", "infra", exclude="")
        assert subs == {}
    finally:
        auth_ctx.reset(token)
        registry.unregister_session("test-session")


async def test_unsubscribe_resource_ignores_uri_for_a_different_project(team, data_path):
    from mcp.types import SubscribeRequestParams, UnsubscribeRequestParams
    from mulchd.mcp.subscriptions import registry

    # subscribe_resource/unsubscribe_resource read session_id from
    # ctx.request.headers, so a bare None for ctx crashes on attribute
    # access before the registry is ever touched — use a minimal stand-in
    # exposing the shape they actually need.
    fake_ctx = SimpleNamespace(
        request=SimpleNamespace(headers={"mcp-session-id": "test-session"}),
        session=object(),
    )

    t = team
    token = auth_ctx.set(ctx(t.carlos, t.org, t.infra))
    try:
        # Register a legitimate subscription for the caller's own project first.
        await subscribe_resource(
            fake_ctx, SubscribeRequestParams(uri="mulchd://acme/infra/domain/infra")
        )
        await unsubscribe_resource(
            fake_ctx, UnsubscribeRequestParams(uri="mulchd://other-org/other-project/domain/infra")
        )
        # The caller's own legitimate subscription is untouched by the
        # mismatched unsubscribe attempt.
        subs = registry.subscribers_for("acme", "infra", "infra", exclude="")
        assert subs != {}
    finally:
        auth_ctx.reset(token)
        registry.unregister_session("test-session")
