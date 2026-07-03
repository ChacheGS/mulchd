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
        '    "mulchd-<project>": {\n'
        '      "type": "http",\n'
        f'      "url": "{base_url}/mcp",\n'
        '      "headers": { "Authorization": "Bearer <your-project-token>" }\n'
        '    }\n'
        '  }\n'
        '}'
    )
    desktop_snippet = (
        '{\n'
        '  "mcpServers": {\n'
        '    "mulchd-<project>": {\n'
        '      "command": "npx",\n'
        '      "args": ["-y", "mcp-remote@latest", "' + base_url + '/mcp",\n'
        '               "--header", "Authorization:${MULCHD_TOKEN}"],\n'
        '      "env": { "MULCHD_TOKEN": "Bearer <your-project-token>" }\n'
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
            "<h2>Add your project-token MCP entry</h2>\n"
            "<p>Replace <code>&lt;project&gt;</code> with your project name and "
            "<code>&lt;your-project-token&gt;</code> with the token your admin gave you.</p>\n"
            "<h3>Claude Code — <code>.mcp.json</code></h3>\n"
            f"<pre>{escape(claude_code_snippet)}</pre>\n"
            "<h3>Claude Desktop — <code>claude_desktop_config.json</code> (requires Node.js/npx)</h3>\n"
            f"<pre>{escape(desktop_snippet)}</pre>\n"
            "<h2>Don't have a token yet?</h2>\n"
            "<p>Ask your admin for a project token, or — if you have a global token — "
            "connect with it and ask Claude to run "
            "<code>mint_project_token</code> to mint one for yourself.</p>\n"
            f"{contact_line}"
            "</body></html>"
        )
    else:
        contact_line = f"\nNeed a token? {admin_contact}\n" if admin_contact else ""
        return (
            f"mulchd server: {base_url}\n\n"
            "== Add your project-token MCP entry ==\n\n"
            "Replace <project> with your project name and <your-project-token> with\n"
            "the token your admin gave you.\n\n"
            "Claude Code (.mcp.json):\n"
            f"{claude_code_snippet}\n\n"
            "Claude Desktop (claude_desktop_config.json, requires Node.js/npx):\n"
            f"{desktop_snippet}\n\n"
            "== Don't have a token yet? ==\n\n"
            "Ask your admin for a project token, or — if you have a global token —\n"
            "connect with it and ask Claude to run mint_project_token to mint one.\n"
            f"{contact_line}"
        )
