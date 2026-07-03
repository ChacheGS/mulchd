from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool

from ..config import settings
from .onboarding import render_onboarding_text

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
    text = render_onboarding_text(base_url, "plain", admin_contact=settings.admin_contact)
    text += f"\n\nFull setup guide: {base_url}/onboard"
    return [TextContent(type="text", text=text)]


@tier1_server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    if name == "get_setup_instructions":
        return await _get_setup_instructions()
    raise ValueError(f"Unknown tool: {name}")
