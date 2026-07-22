# mulchd

Stop re-explaining your stack to every new Claude session — mulchd gives Claude a memory your whole team shares.

mulchd is a self-hosted MCP server that stores and serves structured team knowledge. Engineers record decisions, conventions, and patterns once; every AI session loads exactly what's relevant, attributed to whoever wrote it, without re-prompting.

## How it works

mulchd builds on [mulch](https://github.com/jayminwest/mulch), a CLI that manages structured knowledge as JSONL records on disk. mulchd wraps it with an HTTP server that exposes eight MCP tools over the standard Streamable HTTP and legacy SSE transports:

| Tool | Description |
|---|---|
| `list_domains` | List all knowledge domains and the current server timestamp |
| `read_records` | Load records from one or more domains |
| `write_record` | Record a new decision, convention, pattern, failure, or guide |
| `edit_record` | Update an existing record in place |
| `delete_record` | Soft-delete a record (recoverable from `/admin`) |
| `search_records` | BM25 full-text search across domains |
| `get_recent` | Surface teammate activity since a given timestamp |
| `get_record_schema` | Get required and optional fields for a record type |

Knowledge is organized into domains (e.g. `architecture`, `conventions`, `ops`). Records carry attribution, classification (`foundational` / `tactical` / `observational`), and optional supersession links so the team can track how thinking evolves.

An admin UI at `/admin` covers user and project management, a live record browser, and a full audit log with soft-delete and restore. A self-service `/connect` portal lets team members mint their own project-scoped tokens without admin involvement.

## Try it locally

The demo script seeds a database with sample users, records, and tool-call history, then starts the server:

```bash
git clone https://github.com/ChacheGS/mulchd
cd mulchd
uv sync
./scripts/demo.sh
```

The seed script grants `alice` admin access directly. Open `http://localhost:8000/connect`, log in with alice's printed token, then visit `http://localhost:8000/admin`. The demo creates three users (alice, bob, claude) and a `backend-api` project with records across four domains.

To connect a client to the demo server, use the project tokens printed by the seed script and point it at `http://localhost:8000/mcp`.

## Production setup

Requirements: a VPS with Docker, a domain, and a DNS provider supported by Traefik's ACME challenge (the included config uses DigitalOcean).

**1. Configure environment files**

```bash
cp deploy/mulchd.env.example deploy/mulchd.env
cp deploy/postgres.env.example deploy/postgres.env
cp deploy/traefik.env.example deploy/traefik.env
cp deploy/.env.example deploy/.env
```

Fill in all values. Key variables:

| File | Variable | Description |
|---|---|---|
| `mulchd.env` | `MULCHD_SECRET_KEY` | 64-char hex string — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `mulchd.env` | `MULCHD_BOOTSTRAP_ADMIN_EMAIL` | Email of the first admin — grants access on first SSO login, then goes inert |
| `.env` | `MULCHD_HOSTNAME` | Public hostname, e.g. `mulchd.your-domain.com` |

**2. Deploy**

```bash
docker compose -f deploy/docker-compose.yml up -d
```

Migrations run automatically on each deploy. The admin UI will be at `https://mulchd.your-domain.com/admin`.

**4. Create users**

Log in to `/admin` and create an account for each team member. Each user gets a global token on creation — shown once, used to log in to `/connect`.

**5. Configure SSO (optional)**

To enable GitHub or OIDC sign-in on the `/connect` portal, uncomment and fill in the relevant OAuth vars in `deploy/mulchd.env` (see `mulchd.env.example`). Users must have their email set in the admin before their first SSO login — the server matches the provider's verified email to `User.email` to link the identity automatically.

To hand admin rights to the first person on a fresh instance, set `MULCHD_BOOTSTRAP_ADMIN_EMAIL` to the email of whoever already has a `User` account and should administer the instance, then have them log in via `/connect` as usual — they receive a SUPERADMIN grant on that login. This only fires while no admin exists yet; once any admin grant exists it goes permanently inert, even if the var stays set.

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

## Development

```bash
uv sync
make dev          # start mulchd + postgres with live reload
make test         # run the test suite
make dev-inspector  # start the MCP Inspector on :6274 alongside mulchd
```

`make dev-inspector` is useful for inspecting the MCP protocol directly — subscribe to resources, call tools, and observe notifications without a full AI client.

## Roadmap

- **Automated alerting** — webhook or email notifications when structural audit events fire (cross-owner edits, foundational-record supersessions)
- **Live notifications** — server-side resource subscriptions are implemented and spec-compliant; waiting on client support (`resources/subscribe` is not yet implemented in Claude Code or Codex)
- **Claude Desktop snippets** — `/connect` already generates them; document the flow end-to-end

## Contributing

Issues and pull requests are welcome. For non-trivial changes, open an issue first to discuss the approach — especially anything touching the MCP tool interface or the audit trail, where backward compatibility and security posture matter. Run `make format` and `make test` before submitting.

## Acknowledgements

mulchd builds on [mulch](https://github.com/jayminwest/mulch) by Jaymin West, which provides the JSONL knowledge store, BM25 search, and the `ml` CLI that mulchd shells out to for all record operations. mulch is MIT licensed.
