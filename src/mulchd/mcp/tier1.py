from mcp.server import Server, ServerRequestContext
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ContentBlock,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from .. import __version__
from ..config import settings

TIER1_TOOLS = [
    Tool(
        name="get_setup_instructions",
        description=(
            "Get instructions for setting up mulchd with your MCP client. "
            "Call this if you have no other mulchd tools available."
        ),
        input_schema={"type": "object", "properties": {}},
    ),
]


async def _list_tools(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListToolsResult:
    return ListToolsResult(tools=TIER1_TOOLS)


async def _get_setup_instructions() -> list[ContentBlock]:
    base_url = settings.resolved_base_url
    lines = [
        f"mulchd server: {base_url}",
        "",
        "To connect your MCP client to mulchd:",
        "1. Get a global token from your admin.",
        f"2. Visit {base_url}/connect — enter your token, select a project,",
        "   and mint a project token.",
        "3. Add the project token to your MCP client config",
        "   (the /connect page shows you exactly what to paste).",
        "4. Reconnect — you'll have access to the full knowledge toolset.",
        "",
        f"Setup guide: {base_url}/connect",
    ]
    if settings.admin_contact:
        lines.append(f"Need a token? {settings.admin_contact}")
    return [TextContent(type="text", text="\n".join(lines))]


async def _call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    if params.name == "get_setup_instructions":
        content = await _get_setup_instructions()
        return CallToolResult(content=content, is_error=False)
    return CallToolResult(
        content=[TextContent(type="text", text=f"Unknown tool: {params.name}")],
        is_error=True,
    )


tier1_server = Server(
    "mulchd",
    version=__version__,
    on_list_tools=_list_tools,
    on_call_tool=_call_tool,
)
tier1_manager = StreamableHTTPSessionManager(app=tier1_server, stateless=True)
