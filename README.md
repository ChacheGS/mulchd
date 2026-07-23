# mulchd

Stop re-explaining your stack to every new Claude session — mulchd gives Claude a memory your whole team shares.

mulchd is a self-hosted MCP server that stores and serves structured team knowledge. Engineers record decisions, conventions, and patterns once; every AI session loads exactly what's relevant, attributed to whoever wrote it, without re-prompting.

## How it works

mulchd builds on [mulch](https://github.com/jayminwest/mulch), a CLI that manages structured knowledge as JSONL records on disk, and wraps it with an HTTP server exposing MCP tools (`write_decision`, `search_records`, `get_recent`, and more — see [docs/mcp-tools.md](docs/mcp-tools.md)) over Streamable HTTP and legacy SSE.

Knowledge is organized into domains (e.g. `architecture`, `conventions`, `ops`). Records carry attribution, classification (`foundational` / `tactical` / `observational`), and optional supersession links so the team can track how thinking evolves.

An admin UI at `/admin` covers user and project management, [invite links](docs/features/invite-links.md) for self-service onboarding, [admin access management and an instance-wide activity log](docs/features/admin-rbac.md), a live record browser, and a full per-project record audit log with soft-delete and restore. A self-service `/connect` portal lets team members mint their own project-scoped tokens without admin involvement.

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

See [docs/deployment.md](docs/deployment.md) for the full walkthrough: environment configuration, deploying with Docker Compose, bootstrapping the first admin, creating users, and enabling SSO.

## Connecting a client

mulchd works with any MCP-compatible client. The `/connect` portal generates ready-to-paste config snippets for Claude Code and Claude Desktop — see [docs/mcp-tools.md](docs/mcp-tools.md) for the tool list and example client config.

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
