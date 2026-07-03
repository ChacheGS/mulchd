from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool

from ..config import settings

tier1_server = Server("mulchd")
tier1_manager = StreamableHTTPSessionManager(app=tier1_server, stateless=True)

TIER1_TOOLS = [
    Tool(
        name="get_setup_instructions",
        description=(
            "Get instructions for setting up mulchd with your MCP client. "
            "Call this if you have no other mulchd tools available."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
]


@tier1_server.list_tools()
async def list_tools() -> list[Tool]:
    return TIER1_TOOLS


async def _get_setup_instructions() -> list[TextContent]:
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


@tier1_server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    if name == "get_setup_instructions":
        return await _get_setup_instructions()
    raise ValueError(f"Unknown tool: {name}")
