from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.middleware.sessions import SessionMiddleware
from tortoise import Tortoise

from .admin import router as admin_router
from .auth import AuthContext, Role, authenticate
from .config import TORTOISE_ORM, settings
from .domains import STARTER_DOMAINS, expertise_path, list_available_domains, mulch_dir
from .models import RecordMeta
from .mulch import ensure_domain, search_domains, write_record
from .records import read_domain_records

_ctx: ContextVar[AuthContext | None] = ContextVar("auth_context", default=None)

mcp_server = Server("mulchd")
sse = SseServerTransport("/messages/")
security = HTTPBearer()

# ---------------------------------------------------------------------------
# MCP tool registry
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="read_expertise",
        description=(
            "Load team expertise records for context injection at session start. "
            "Call this at the beginning of a session with domains relevant to the current task."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Domain names to read from.",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Max records to return across all domains.",
                },
            },
            "required": ["domains"],
        },
    ),
    Tool(
        name="record_expertise",
        description=(
            "Write a new expertise record to a domain. Call this when a decision, "
            "convention, failure, or pattern has been reached — without being asked."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["convention", "pattern", "failure", "decision", "reference", "guide"],
                },
                "classification": {
                    "type": "string",
                    "enum": ["foundational", "tactical", "observational"],
                },
                "content": {
                    "type": "object",
                    "description": (
                        "Type-specific fields. convention: {content}. "
                        "pattern/reference/guide: {name, description}. "
                        "failure: {description, resolution}. "
                        "decision: {title, rationale}."
                    ),
                },
                "session_id": {
                    "type": "string",
                    "description": "UUID identifying the current session. Generate once per session.",
                },
                "client": {
                    "type": "string",
                    "description": "Client identifier, e.g. claude-desktop or claude-code.",
                },
            },
            "required": ["domain", "type", "classification", "content"],
        },
    ),
    Tool(
        name="search_expertise",
        description="Search expertise records by query, optionally filtered by domain or author.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Limit search to these domains. Defaults to all domains.",
                },
                "author": {
                    "type": "string",
                    "description": "Filter to records written by this username.",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="list_domains",
        description="List available domains with record counts and last-updated timestamps.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_recent",
        description=(
            "Get expertise records written since a given timestamp. "
            "Call at session end to surface changes made by teammates while you were working."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "since": {
                    "type": "string",
                    "description": "ISO 8601 timestamp. Returns records recorded after this time.",
                },
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Limit to these domains. Defaults to all domains.",
                },
            },
            "required": ["since"],
        },
    ),
]


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    args = arguments or {}
    ctx = _ctx.get()
    if ctx is None:
        raise ValueError("No auth context in scope")

    match name:
        case "read_expertise":
            return await _read_expertise(args, ctx)
        case "record_expertise":
            return await _record_expertise(args, ctx)
        case "search_expertise":
            return await _search_expertise(args, ctx)
        case "list_domains":
            return await _list_domains(ctx)
        case "get_recent":
            return await _get_recent(args, ctx)
        case _:
            raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _read_expertise(args: dict, ctx: AuthContext) -> list[TextContent]:
    domains = args.get("domains", [])
    limit = int(args.get("limit", 50))
    all_records: list[dict] = []
    for domain in domains:
        records = await read_domain_records(expertise_path(ctx.org.slug, ctx.project.slug, domain))
        for r in records:
            r["_domain"] = domain
        all_records.extend(records)
    return [TextContent(type="text", text=_format_records(all_records[:limit]))]


async def _record_expertise(args: dict, ctx: AuthContext) -> list[TextContent]:
    if ctx.role == Role.READER:
        raise ValueError("reader role cannot write records")

    domain = args["domain"]
    record = {
        "type": args["type"],
        "classification": args["classification"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "owner": ctx.user.username,
        **args.get("content", {}),
    }

    m_dir = mulch_dir(ctx.org.slug, ctx.project.slug)
    await ensure_domain(m_dir, domain)
    written = await write_record(m_dir, domain, record)

    session_id = UUID(args["session_id"]) if "session_id" in args else uuid4()
    await RecordMeta.create(
        record_id=written["id"],
        project=ctx.project,
        domain=domain,
        author=ctx.user,
        session_id=session_id,
        client=args.get("client", "unknown"),
    )

    return [
        TextContent(type="text", text=f"Recorded {written['type']} in {domain} ({written['id']})")
    ]


async def _search_expertise(args: dict, ctx: AuthContext) -> list[TextContent]:
    query = args["query"]
    # Pass explicit domains list or None to let mulch search all configured domains.
    domains: list[str] | None = args.get("domains") or None
    author_filter = args.get("author")

    results = await search_domains(mulch_dir(ctx.org.slug, ctx.project.slug), query, domains)

    if author_filter:
        results = [r for r in results if r.get("owner") == author_filter]

    return [TextContent(type="text", text=_format_records(results))]


async def _list_domains(ctx: AuthContext) -> list[TextContent]:
    domains = await list_available_domains(ctx.org.slug, ctx.project.slug)
    lines = [f"# Domains — {ctx.org.display_name} / {ctx.project.display_name}\n"]
    for d in domains:
        updated = d["last_updated"] or "never"
        lines.append(f"**{d['name']}** — {d['description']}")
        lines.append(f"  {d['record_count']} records, last updated: {updated}\n")
    return [TextContent(type="text", text="\n".join(lines))]


async def _get_recent(args: dict, ctx: AuthContext) -> list[TextContent]:
    since = datetime.fromisoformat(args["since"])
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    domains = args.get("domains") or list(STARTER_DOMAINS)

    results: list[dict] = []
    for domain in domains:
        for r in await read_domain_records(expertise_path(ctx.org.slug, ctx.project.slug, domain)):
            ts = r.get("recorded_at", "2000-01-01T00:00:00+00:00")
            recorded_at = datetime.fromisoformat(ts)
            if recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=timezone.utc)
            if recorded_at >= since:
                r["_domain"] = domain
                results.append(r)

    results.sort(key=lambda r: r.get("recorded_at", ""), reverse=True)
    return [TextContent(type="text", text=_format_records(results))]


def _format_records(records: list[dict]) -> str:
    if not records:
        return "No records found."
    lines: list[str] = []
    for r in records:
        owner = r.get("owner", "")
        rid = r.get("id", "?")
        recorded_at = r.get("recorded_at", "")[:10]
        main = r.get("content") or r.get("rationale") or r.get("description") or r.get("name") or ""
        author_str = f" by {owner}" if owner else ""
        lines.append(
            f"[{r.get('_domain')}/{r.get('type')}/{r.get('classification')}]"
            f" {rid}{author_str} ({recorded_at})"
        )
        lines.append(f"  {str(main)[:200]}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_: FastAPI):
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()
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


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    org: str = Query(..., description="Organisation slug"),
    project: str = Query(..., description="Project slug"),
) -> AuthContext:
    ctx = await authenticate(credentials.credentials, org, project)
    if ctx is None:
        raise HTTPException(status_code=401, detail="Invalid token or no access to this project")
    return ctx


@app.get("/sse")
async def sse_endpoint(request: Request, ctx: AuthContext = Depends(get_auth_context)):
    _ctx.set(ctx)
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(streams[0], streams[1], mcp_server.create_initialization_options())


@app.post("/messages/")
async def handle_messages(request: Request):
    await sse.handle_post_message(request.scope, request.receive, request._send)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def run() -> None:
    import uvicorn

    uvicorn.run("server.main:app", host=settings.host, port=settings.port, reload=False)
