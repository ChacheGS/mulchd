# MCP tools and connecting a client

mulchd builds on [mulch](https://github.com/jayminwest/mulch), a CLI that manages structured knowledge as JSONL records on disk. mulchd wraps it with an HTTP server that exposes these MCP tools over the standard Streamable HTTP and legacy SSE transports:

| Tool | Description |
|---|---|
| `list_domains` | List all knowledge domains and the current server timestamp |
| `read_records` | Load records from one or more domains |
| `write_decision` | Record a decision that's been made or confirmed |
| `write_convention` | Record a convention that's been established or corrected |
| `write_failure` | Record something that broke and how it got fixed |
| `write_pattern` | Record a reusable solution or code shape |
| `write_reference` | Record a pointer to external info worth remembering |
| `write_guide` | Record a how-to guide |
| `edit_record` | Update an existing record in place |
| `delete_record` | Soft-delete a record (recoverable from `/admin`) |
| `search_records` | BM25 full-text search across domains |
| `get_recent` | Surface teammate activity since a given timestamp |
| `get_record_schema` | Get required and optional fields for a record type |

Knowledge is organized into domains (e.g. `architecture`, `conventions`, `ops`). Records carry attribution, classification (`foundational` / `tactical` / `observational`), and optional supersession links so the team can track how thinking evolves.

## Connecting a client

mulchd works with any MCP-compatible client. The `/connect` portal generates ready-to-paste config snippets for Claude Code and Claude Desktop — use those rather than hand-editing.

For Claude Code, the generated `.mcp.json` entry looks like:

```json
{
  "mcpServers": {
    "mulchd": {
      "type": "http",
      "url": "https://mulchd.your-domain.com/mcp",
      "headers": {
        "Authorization": "Bearer ${MULCHD_TOKEN_YOUR_PROJECT}"
      }
    }
  }
}
```

The token goes in `.claude/settings.local.json` (not committed):

```json
{
  "env": {
    "MULCHD_TOKEN_YOUR_PROJECT": "mlt_..."
  }
}
```

For clients that use the legacy SSE transport, the endpoint is `/sse` with the same `Authorization` header.
