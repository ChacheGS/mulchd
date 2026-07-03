from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool

from ..auth import create_project_token
from ..config import settings
from ..models import Project, ProjectToken, UserMembership
from .context import _global_ctx

tier2_server = Server("mulchd")
tier2_manager = StreamableHTTPSessionManager(app=tier2_server, stateless=True)

TIER2_TOOLS = [
    Tool(
        name="list_my_projects",
        description="List all projects you have access to.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="mint_project_token",
        description=(
            "Mint a new project-scoped token. Returns the token and exact MCP config "
            "snippets for both Claude Code and Claude Desktop. Check list_project_tokens "
            "first to avoid creating duplicates."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "org": {"type": "string", "description": "Organisation slug"},
                "project": {"type": "string", "description": "Project slug"},
                "label": {"type": "string", "description": "Human-readable label (optional)"},
            },
            "required": ["org", "project"],
        },
    ),
    Tool(
        name="list_project_tokens",
        description="List your active tokens for a project.",
        inputSchema={
            "type": "object",
            "properties": {
                "org": {"type": "string"},
                "project": {"type": "string"},
            },
            "required": ["org", "project"],
        },
    ),
    Tool(
        name="revoke_project_token",
        description="Revoke a project token by its ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "org": {"type": "string"},
                "project": {"type": "string"},
                "token_id": {"type": "integer"},
            },
            "required": ["org", "project", "token_id"],
        },
    ),
]


def _build_next_steps(base_url: str, org: str, project: str, token: str) -> str:
    env_var = (
        f"MULCHD_TOKEN_{org.upper().replace('-', '_')}_{project.upper().replace('-', '_')}"
    )
    return (
        f"Token minted for {org}/{project}.\n\n"
        f"Claude Code — add to .mcp.json:\n"
        f'{{\n'
        f'  "mcpServers": {{\n'
        f'    "mulchd-{project}": {{\n'
        f'      "type": "http",\n'
        f'      "url": "{base_url}/mcp",\n'
        f'      "headers": {{ "Authorization": "Bearer {token}" }}\n'
        f'    }}\n'
        f'  }}\n'
        f'}}\n\n'
        f"Claude Desktop — add to claude_desktop_config.json (requires Node.js/npx):\n"
        f'{{\n'
        f'  "mcpServers": {{\n'
        f'    "mulchd-{org}-{project}": {{\n'
        f'      "command": "npx",\n'
        f'      "args": ["-y", "mcp-remote@latest", "{base_url}/mcp",\n'
        f'               "--header", "Authorization:${{{env_var}}}"],\n'
        f'      "env": {{ "{env_var}": "Bearer {token}" }}\n'
        f'    }}\n'
        f'  }}\n'
        f'}}\n\n'
        f"Then restart your client and reconnect — this connection authenticates as "
        f"the {org}/{project} token and unlocks the knowledge tools."
    )


async def _get_accessible_project(user, org_slug: str, project_slug: str) -> Project:
    project = (
        await Project.filter(slug=project_slug, org__slug=org_slug)
        .select_related("org")
        .first()
    )
    if project is None:
        raise ValueError(f"Project {org_slug}/{project_slug} not found")
    membership = await UserMembership.filter(user=user, project=project).first()
    if membership is None:
        raise ValueError(f"No access to {org_slug}/{project_slug}")
    return project


async def _list_my_projects(user) -> list[TextContent]:
    memberships = (
        await UserMembership.filter(user=user).select_related("project__org").all()
    )
    if not memberships:
        return [TextContent(type="text", text="You have no project memberships.")]
    lines = ["Your projects:\n"]
    for m in memberships:
        lines.append(f"  {m.project.org.slug}/{m.project.slug} — {m.role}")
    return [TextContent(type="text", text="\n".join(lines))]


async def _mint_project_token(args: dict, user) -> list[TextContent]:
    org = args["org"]
    project_slug = args["project"]
    label = args.get("label", "")
    project = await _get_accessible_project(user, org, project_slug)
    pt, raw_token = await create_project_token(user, project, label=label)
    next_steps = _build_next_steps(settings.resolved_base_url, org, project_slug, raw_token)
    return [TextContent(type="text", text=next_steps)]


async def _list_project_tokens(args: dict, user) -> list[TextContent]:
    org = args["org"]
    project_slug = args["project"]
    project = await _get_accessible_project(user, org, project_slug)
    tokens = await ProjectToken.filter(user=user, project=project, active=True).all()
    if not tokens:
        return [TextContent(type="text", text="No active tokens for this project.")]
    lines = [f"Active tokens for {org}/{project_slug}:\n"]
    for t in tokens:
        label = f" ({t.label})" if t.label else ""
        lines.append(f"  id={t.id}{label} — created {str(t.created_at)[:10]}")
    return [TextContent(type="text", text="\n".join(lines))]


async def _revoke_project_token(args: dict, user) -> list[TextContent]:
    org = args["org"]
    project_slug = args["project"]
    token_id = int(args["token_id"])
    project = await _get_accessible_project(user, org, project_slug)
    updated = await ProjectToken.filter(
        id=token_id, user=user, project=project, active=True
    ).update(active=False)
    if not updated:
        raise ValueError(f"Token {token_id} not found or already revoked")
    return [TextContent(type="text", text=f"Token {token_id} revoked.")]


@tier2_server.list_tools()
async def list_tools() -> list[Tool]:
    return TIER2_TOOLS


@tier2_server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    user = _global_ctx.get()
    if user is None:
        raise ValueError("No global auth context — use a global token for this connection")
    args = arguments or {}
    match name:
        case "list_my_projects":
            return await _list_my_projects(user)
        case "mint_project_token":
            return await _mint_project_token(args, user)
        case "list_project_tokens":
            return await _list_project_tokens(args, user)
        case "revoke_project_token":
            return await _revoke_project_token(args, user)
        case _:
            raise ValueError(f"Unknown tool: {name}")
