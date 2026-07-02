from html import escape
from typing import Literal


def render_onboarding_text(
    base_url: str,
    format: Literal["html", "plain"],
    admin_contact: str | None = None,
) -> str:
    claude_code_snippet = (
        '{\n'
        '  "mcpServers": {\n'
        '    "mulchd": {\n'
        '      "type": "http",\n'
        f'      "url": "{base_url}/mcp",\n'
        '      "headers": { "Authorization": "Bearer <your-global-token>" }\n'
        '    }\n'
        '  }\n'
        '}'
    )
    desktop_snippet = (
        '{\n'
        '  "mcpServers": {\n'
        '    "mulchd": {\n'
        '      "command": "npx",\n'
        '      "args": ["-y", "mcp-remote@latest", "' + base_url + '/mcp",\n'
        '               "--header", "Authorization:${MULCHD_TOKEN}"],\n'
        '      "env": { "MULCHD_TOKEN": "Bearer <your-global-token>" }\n'
        '    }\n'
        '  }\n'
        '}'
    )

    if format == "html":
        contact_line = f"<p><strong>Need a token?</strong> {admin_contact}</p>\n" if admin_contact else ""
        return (
            "<!DOCTYPE html><html><head><title>mulchd setup</title>"
            "<style>body{font-family:system-ui;max-width:800px;margin:40px auto;padding:0 20px}"
            "pre{background:#f1f5f9;padding:16px;border-radius:6px;overflow-x:auto}"
            "code{font-family:monospace}</style></head><body>\n"
            "<h1>mulchd setup</h1>\n"
            f"<p>Server: <code>{base_url}</code></p>\n"
            "<h2>Step 1: Add a global-token MCP entry</h2>\n"
            "<p>This lets Claude mint project tokens for you.</p>\n"
            "<h3>Claude Code — <code>.mcp.json</code></h3>\n"
            f"<pre>{escape(claude_code_snippet)}</pre>\n"
            "<h3>Claude Desktop — <code>claude_desktop_config.json</code> (requires Node.js/npx)</h3>\n"
            f"<pre>{escape(desktop_snippet)}</pre>\n"
            "<h2>Step 2: Ask Claude to mint a project token</h2>\n"
            "<p>Once connected with a global token, ask Claude to run "
            "<code>mint_project_token</code> for your project. It will give you the exact "
            "config snippet for a project-scoped connection.</p>\n"
            f"{contact_line}"
            "</body></html>"
        )
    else:
        contact_line = f"\nNeed a token? {admin_contact}\n" if admin_contact else ""
        return (
            f"mulchd server: {base_url}\n\n"
            "== Step 1: Add a global-token MCP entry ==\n\n"
            "Claude Code (.mcp.json):\n"
            f"{claude_code_snippet}\n\n"
            "Claude Desktop (claude_desktop_config.json, requires Node.js/npx):\n"
            f"{desktop_snippet}\n\n"
            "== Step 2: Ask Claude to mint a project token ==\n\n"
            "Once connected with a global token, ask Claude to run mint_project_token\n"
            "for your project. It will give you the exact config snippet for a\n"
            "project-scoped connection.\n"
            f"{contact_line}"
        )
