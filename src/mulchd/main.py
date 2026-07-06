from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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


@app.api_route("/mcp", methods=["GET", "POST", "DELETE"])
async def mcp_endpoint(request: Request) -> None:
    tier, ctx = await resolve_mcp_tier(request)
    if tier == "tier2":
        _ctx.set(ctx)
    await tier_managers[tier].handle_request(request.scope, request.receive, request._send)


@app.get("/sse")
async def sse_endpoint(request: Request):
    tier, ctx = await resolve_mcp_tier(request)
    if tier == "tier2":
        _ctx.set(ctx)
    server = tier_servers[tier]
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


@app.post("/messages/")
async def handle_messages(request: Request):
    await sse.handle_post_message(request.scope, request.receive, request._send)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def run() -> None:
    import uvicorn

    uvicorn.run("mulchd.main:app", host=settings.host, port=settings.port, reload=settings.reload)
