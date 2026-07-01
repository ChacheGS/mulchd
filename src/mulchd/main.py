from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.middleware.sessions import SessionMiddleware
from tortoise import Tortoise

from .admin import router as admin_router
from .api import router as api_router
from .auth import AuthContext, Role, authenticate_project_token
from .config import TORTOISE_ORM, settings
from .domains import expertise_path, list_available_domains, mulch_dir
from .models import RecordMeta
from .mulch import delete_record, edit_record, ensure_domain, search_domains, write_record
from .records import find_record, read_domain_records

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
    Tool(
        name="get_record_schema",
        description=(
            "Return the required and optional content fields for one or all record types. "
            "Call this before record_expertise or edit_record to avoid field-name errors."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["convention", "pattern", "failure", "decision", "reference", "guide"],
                    "description": "Omit to return schemas for all types.",
                },
            },
        },
    ),
    Tool(
        name="edit_record",
        description=(
            "Update fields on an existing expertise record. "
            "Writers may only edit their own records; admins may edit any record. "
            "Pass only the fields you want to change."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "Record ID (mx-xxxxxx)"},
                "domain": {"type": "string"},
                "classification": {
                    "type": "string",
                    "enum": ["foundational", "tactical", "observational"],
                },
                "title": {"type": "string", "description": "decision: title field"},
                "rationale": {"type": "string", "description": "decision: rationale field"},
                "content": {"type": "string", "description": "convention: body text"},
                "description": {
                    "type": "string",
                    "description": "failure/pattern/reference/guide: description field",
                },
                "resolution": {"type": "string", "description": "failure: resolution field"},
                "name": {
                    "type": "string",
                    "description": "pattern/reference/guide: name field",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Related file paths",
                },
                "relates_to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Related record IDs",
                },
                "supersedes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Record IDs this record replaces",
                },
            },
            "required": ["record_id", "domain"],
        },
    ),
    Tool(
        name="delete_record",
        description=(
            "Delete an expertise record by ID. "
            "Writers may only delete their own records; admins may delete any record."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "Record ID (mx-xxxxxx)"},
                "domain": {"type": "string"},
            },
            "required": ["record_id", "domain"],
        },
    ),
]

_RECORD_SCHEMAS: dict[str, dict] = {
    "convention": {
        "required": {"content": "string"},
        "optional": {},
    },
    "decision": {
        "required": {"title": "string", "rationale": "string"},
        "optional": {"date": "string"},
    },
    "failure": {
        "required": {"description": "string", "resolution": "string"},
        "optional": {},
    },
    "pattern": {
        "required": {"name": "string", "description": "string"},
        "optional": {"files": "array of strings"},
    },
    "reference": {
        "required": {"name": "string", "description": "string"},
        "optional": {"files": "array of strings"},
    },
    "guide": {
        "required": {"name": "string", "description": "string"},
        "optional": {},
    },
}


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
        case "get_record_schema":
            return await _get_record_schema(args)
        case "edit_record":
            return await _edit_record(args, ctx)
        case "delete_record":
            return await _delete_record(args, ctx)
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
    if args.get("domains"):
        domains = args["domains"]
    else:
        domains = [d["name"] for d in await list_available_domains(ctx.org.slug, ctx.project.slug)]

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


async def _get_record_schema(args: dict) -> list[TextContent]:
    type_filter = args.get("type")
    schemas = {type_filter: _RECORD_SCHEMAS[type_filter]} if type_filter else _RECORD_SCHEMAS
    lines = ["# Record type schemas\n"]
    for rtype, schema in schemas.items():
        req = ", ".join(f"`{k}` ({v})" for k, v in schema["required"].items())
        opt = ", ".join(f"`{k}` ({v})" for k, v in schema["optional"].items())
        lines.append(f"**{rtype}**")
        lines.append(f"  required: {req or 'none'}")
        if opt:
            lines.append(f"  optional: {opt}")
        lines.append("")
    return [TextContent(type="text", text="\n".join(lines))]


async def _edit_record(args: dict, ctx: AuthContext) -> list[TextContent]:
    if ctx.role == Role.READER:
        raise ValueError("reader role cannot edit records")

    record_id = args["record_id"]
    domain = args["domain"]

    record = await find_record(expertise_path(ctx.org.slug, ctx.project.slug, domain), record_id)
    if record is None:
        raise ValueError(f"record {record_id} not found in domain {domain}")

    if ctx.role != Role.ADMIN and record.get("owner") != ctx.user.username:
        raise ValueError("you can only edit your own records (writer role)")

    update_keys = {
        "classification", "title", "rationale", "content", "description",
        "resolution", "name", "files", "relates_to", "supersedes",
    }
    updates = {k: args[k] for k in update_keys if k in args}
    if not updates:
        raise ValueError("no fields to update — pass at least one content field")

    await edit_record(mulch_dir(ctx.org.slug, ctx.project.slug), domain, record_id, updates)
    return [TextContent(type="text", text=f"Updated {record_id} in {domain}")]


async def _delete_record(args: dict, ctx: AuthContext) -> list[TextContent]:
    if ctx.role == Role.READER:
        raise ValueError("reader role cannot delete records")

    record_id = args["record_id"]
    domain = args["domain"]

    record = await find_record(expertise_path(ctx.org.slug, ctx.project.slug, domain), record_id)
    if record is None:
        raise ValueError(f"record {record_id} not found in domain {domain}")

    if ctx.role != Role.ADMIN and record.get("owner") != ctx.user.username:
        raise ValueError("you can only delete your own records (writer role)")

    await delete_record(mulch_dir(ctx.org.slug, ctx.project.slug), domain, record_id)
    return [TextContent(type="text", text=f"Deleted {record_id} from {domain}")]


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
app.include_router(api_router)


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthContext:
    ctx = await authenticate_project_token(credentials.credentials)
    if ctx is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive project token. Use a project-scoped token for MCP access.",
        )
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


_SKILL_PATH = Path(__file__).parent / "skill.md"


@app.get("/skill", response_class=PlainTextResponse)
async def skill(request: Request) -> str:
    text = _SKILL_PATH.read_text()
    base = str(request.base_url).rstrip("/")
    return text.replace("https://SERVER_URL", base).replace("SERVER_URL", base)


def run() -> None:
    import uvicorn

    uvicorn.run("mulchd.main:app", host=settings.host, port=settings.port, reload=False)
