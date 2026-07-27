from contextlib import asynccontextmanager
from importlib.metadata import version as _pkg_version

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from mcp.server.auth.routes import (
    build_resource_metadata_url,
    create_auth_routes,
    create_protected_resource_routes,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.server.sse import SseServerTransport
from pydantic import AnyHttpUrl
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from tortoise import Tortoise

from .admin import router as admin_router
from .api import router as api_router
from .auth import AuthContext, authenticate_project_token
from .config import TORTOISE_ORM, settings
from .connect import router as connect_router
from .invite import router as invite_router
from .mcp import McpTier, tier_managers, tier_servers
from .mcp.context import _ctx
from .mcp_auth import MulchdOAuthProvider, is_known_oauth_token
from .models import Project, User, UserMembership

sse = SseServerTransport("/messages/")


def _client_from_request(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    return ua[:128] if ua else "unknown"


oauth_provider = MulchdOAuthProvider()


async def _auth_context_from_access_token(access_token) -> AuthContext | None:
    user = await User.filter(id=int(access_token.subject), active=True).first()
    if user is None:
        return None
    project_id = (access_token.claims or {}).get("project_id")
    project = await Project.filter(id=project_id).select_related("org").first()
    if project is None:
        return None
    membership = await UserMembership.filter(user=user, project=project).first()
    if membership is None:
        return None
    return AuthContext(user=user, project=project, org=project.org, role=membership.role)


async def resolve_mcp_tier(request: Request) -> tuple[McpTier, AuthContext | None]:
    """
    Returns (tier, ctx). McpTier.INVALID_OAUTH_TOKEN means: this bearer token was minted
    by mulchd's OAuth authorization server, but has since expired or been revoked.
    Callers must answer that case with 401 + WWW-Authenticate, not serve it as tier1 —
    see mcp_endpoint/sse_endpoint below.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return McpTier.TIER1, None
    token = header[7:]

    if settings.mcp_oauth_enabled:
        access_token = await oauth_provider.load_access_token(token)
        if access_token is not None:
            ctx = await _auth_context_from_access_token(access_token)
            if ctx is not None:
                ctx.client = _client_from_request(request)
                return McpTier.TIER2, ctx
        elif await is_known_oauth_token(token):
            return McpTier.INVALID_OAUTH_TOKEN, None

    ctx = await authenticate_project_token(token)
    if ctx is not None:
        ctx.client = _client_from_request(request)
        return McpTier.TIER2, ctx
    return McpTier.TIER1, None


def _oauth_invalid_token_response() -> Response:
    resource_metadata = build_resource_metadata_url(AnyHttpUrl(f"{settings.resolved_base_url}/mcp"))
    www_authenticate = f'Bearer error="invalid_token", resource_metadata="{resource_metadata}"'
    return Response(
        status_code=401,
        content='{"error":"invalid_token","error_description":"The access token expired or was revoked"}',
        media_type="application/json",
        headers={"WWW-Authenticate": www_authenticate},
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    import logging

    # Configure mcp/mulchd loggers here (after uvicorn's dictConfig has run)
    # so our handler and level are not overridden.
    level = settings.log_level.upper()
    _handler = logging.StreamHandler()
    _handler.setLevel(level)
    for _name in ("mcp", "mulchd"):
        _lg = logging.getLogger(_name)
        _lg.setLevel(level)
        if not _lg.handlers:
            _lg.addHandler(_handler)

    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()
    async with (
        tier_managers["tier1"].run(),
        tier_managers["tier2"].run(),
    ):
        yield
    await Tortoise.close_connections()


app = FastAPI(title="mulchd", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="mulchd_session",
    https_only=False,
)
app.include_router(admin_router)
app.include_router(api_router)
app.include_router(connect_router)
app.include_router(invite_router)

if settings.mcp_oauth_enabled:
    issuer_url = AnyHttpUrl(settings.resolved_base_url)
    auth_routes = create_auth_routes(
        provider=oauth_provider,
        issuer_url=issuer_url,
        client_registration_options=ClientRegistrationOptions(enabled=True),
        revocation_options=RevocationOptions(enabled=True),
    )
    resource_routes = create_protected_resource_routes(
        resource_url=AnyHttpUrl(f"{settings.resolved_base_url}/mcp"),
        authorization_servers=[issuer_url],
        resource_name="mulchd",
    )
    app.router.routes.extend(auth_routes)
    app.router.routes.extend(resource_routes)


class _SseNoop(Response):
    # Both /mcp and /sse transports own their full response lifecycle via the
    # raw send callable. This sentinel tells FastAPI not to send a second
    # response after the transport handler returns.
    async def __call__(self, scope, receive, send) -> None:
        pass


@app.api_route("/mcp", methods=["GET", "POST", "DELETE"])
async def mcp_endpoint(request: Request) -> Response:
    tier, ctx = await resolve_mcp_tier(request)
    if tier == McpTier.INVALID_OAUTH_TOKEN:
        return _oauth_invalid_token_response()
    if tier == McpTier.TIER2:
        _ctx.set(ctx)
    await tier_managers[tier].handle_request(request.scope, request.receive, request._send)
    return _SseNoop()


@app.get("/sse")
async def sse_endpoint(request: Request) -> Response:
    tier, ctx = await resolve_mcp_tier(request)
    if tier == McpTier.INVALID_OAUTH_TOKEN:
        return _oauth_invalid_token_response()
    if tier == McpTier.TIER2:
        _ctx.set(ctx)
    server = tier_servers[tier]
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())
    return _SseNoop()


# handle_post_message is a raw ASGI callable — mounting it directly prevents
# FastAPI from trying to send a second response after it has already sent 202.
app.mount("/messages", app=sse.handle_post_message)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": _pkg_version("mulchd")}


def run() -> None:
    import logging
    import uvicorn

    level = settings.log_level.upper()
    # uvicorn only configures its own loggers; "mcp" and "mulchd" propagate to
    # the root logger whose handler defaults to WARNING, dropping DEBUG records.
    # Give them dedicated handlers so the configured level is respected.
    _handler = logging.StreamHandler()
    _handler.setLevel(level)
    for _name in ("mcp", "mulchd"):
        _lg = logging.getLogger(_name)
        _lg.setLevel(level)
        _lg.addHandler(_handler)

    uvicorn.run(
        "mulchd.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
