from contextlib import asynccontextmanager
from importlib.metadata import version as _pkg_version

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from starlette.responses import Response
from mcp.server.sse import SseServerTransport
from starlette.middleware.sessions import SessionMiddleware
from tortoise import Tortoise

from .admin import router as admin_router
from .api import router as api_router
from .auth import AuthContext, authenticate_project_token
from .config import TORTOISE_ORM, settings
from .connect import router as connect_router
from .mcp import tier_managers, tier_servers
from .mcp.context import _ctx

sse = SseServerTransport("/messages/")


def _client_from_request(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    return ua[:128] if ua else "unknown"


async def resolve_mcp_tier(request: Request) -> tuple[str, AuthContext | None]:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return "tier1", None
    token = header[7:]
    ctx = await authenticate_project_token(token)
    if ctx is not None:
        ctx.client = _client_from_request(request)
        return "tier2", ctx
    return "tier1", None


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


class _SseNoop(Response):
    # Both /mcp and /sse transports own their full response lifecycle via the
    # raw send callable. This sentinel tells FastAPI not to send a second
    # response after the transport handler returns.
    async def __call__(self, scope, receive, send) -> None:
        pass


@app.api_route("/mcp", methods=["GET", "POST", "DELETE"])
async def mcp_endpoint(request: Request) -> _SseNoop:
    tier, ctx = await resolve_mcp_tier(request)
    if tier == "tier2":
        _ctx.set(ctx)
    await tier_managers[tier].handle_request(request.scope, request.receive, request._send)
    return _SseNoop()


@app.get("/sse")
async def sse_endpoint(request: Request) -> _SseNoop:
    tier, ctx = await resolve_mcp_tier(request)
    if tier == "tier2":
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
