import logging
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
from .admin._shared import AdminRequired, is_admin, redirect_login
from .api import router as api_router
from .auth import AuthContext, authenticate_project_token
from .config import TORTOISE_ORM, settings
from .connect import get_connect_user_id
from .connect import router as connect_router
from .invite import router as invite_router
from .mcp import McpTier, tier_managers, tier_servers
from .mcp.context import _ctx
from .mcp_auth import MulchdOAuthProvider, is_known_oauth_token
from .models import Project, Role, User, UserMembership, min_role

sse = SseServerTransport("/messages/")
_log = logging.getLogger("mulchd.main")


def _client_from_request(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    return ua[:128] if ua else "unknown"


oauth_provider = MulchdOAuthProvider()


async def _auth_context_from_access_token(access_token) -> AuthContext | None:
    user = await User.filter(id=int(access_token.subject), active=True).first()
    if user is None:
        return None
    claims = access_token.claims or {}
    project_id = claims.get("project_id")
    project = await Project.filter(id=project_id).select_related("org").first()
    if project is None:
        return None
    membership = await UserMembership.filter(user=user, project=project).first()
    if membership is None:
        return None
    granted_role = Role(claims["granted_role"]) if claims.get("granted_role") else membership.role
    return AuthContext(user=user, project=project, org=project.org, role=min_role(membership.role, granted_role))


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
        tier_managers[McpTier.TIER1].run(),
        tier_managers[McpTier.TIER2].run(),
    ):
        yield
    await Tortoise.close_connections()


app = FastAPI(title="mulchd", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="mulchd_session",
    https_only=settings.is_https,
)


@app.middleware("http")
async def _connect_admin_context(request: Request, call_next):
    """Only /connect pages need to know whether the current user is an admin
    (to show/hide the Admin link) — scoping the extra DB query to this prefix
    keeps every other request (MCP calls, health checks, /admin itself, which
    already has its own auth) from paying for it."""
    if request.url.path.startswith("/connect"):
        request.state.is_admin_user = await is_admin(request)
    return await call_next(request)


@app.middleware("http")
async def _admin_project_switcher_context(request: Request, call_next):
    """The sidebar's project switcher (base.html) needs the full project list
    on every /admin page, not just ones that already resolve a `project` —
    computed once here instead of duplicated in every admin route. Gated to
    GET requests: admin POST endpoints all follow the PRG pattern (redirect
    303 after write, decision mx-792f52) and never render base.html, so the
    query would be pure waste there. Also skips /admin/api/ and
    /admin/records/count, which are GET but return JSON, not base.html —
    records/count in particular is polled every 15s by the Records page
    while it's open. Requests with no connect session cookie at all (e.g.
    unauthenticated scanning traffic) skip the query too — require_admin
    would reject them anyway once this middleware hands off, so there's no
    point paying for a project list that will never be rendered. This is a
    cheap local signature check (get_connect_user_id), not a DB call —
    a forged or expired cookie still costs one query, same as a logged-in
    non-admin user, matching the tradeoff already accepted for
    _connect_admin_context above."""
    path = request.url.path
    if (
        request.method == "GET"
        and path.startswith("/admin")
        and not path.startswith("/admin/api/")
        and path != "/admin/records/count"
        and get_connect_user_id(request) is not None
    ):
        request.state.all_projects = await Project.all().order_by("org__slug", "slug").prefetch_related("org")
    return await call_next(request)


app.include_router(admin_router)
app.include_router(api_router)
app.include_router(connect_router)
app.include_router(invite_router)


@app.exception_handler(AdminRequired)
async def _admin_required_handler(request: Request, exc: AdminRequired) -> Response:
    return redirect_login()


if settings.mcp_oauth_enabled:
    # create_auth_routes validates the issuer URL (RFC 8414 requires HTTPS, with a
    # localhost/127.0.0.1 carve-out for local testing) and raises ValueError if it
    # doesn't qualify. resolved_base_url falls back to http://{host}:{port} — with
    # this project's own default settings (host=0.0.0.0, no MULCHD_BASE_URL), that
    # fallback always fails validation. A deployer enabling mcp_oauth_enabled's
    # default without also setting MULCHD_BASE_URL to a real https:// URL must not
    # bring down the entire app (admin UI, /connect, tier1/tier2 MCP included) over
    # an OAuth-specific misconfiguration — degrade to "OAuth AS routes unavailable"
    # instead, and say why.
    issuer_url = AnyHttpUrl(settings.resolved_base_url)
    try:
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
    except ValueError as exc:
        _log.warning(
            "MCP OAuth authorization server routes not registered (issuer URL "
            "%r invalid: %s). Set MULCHD_BASE_URL to a public https:// URL to "
            "enable OAuth-based MCP client connections; falling back to "
            "project-token-only authentication for /mcp.",
            settings.resolved_base_url,
            exc,
        )
    else:
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
