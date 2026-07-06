# mulchd

Stop re-explaining your stack to every new Claude session — mulchd gives Claude a memory your whole team shares.

mulchd is a self-hosted MCP server that stores and serves structured team knowledge. Engineers record decisions, conventions, and patterns once; every Claude session loads exactly what's relevant, attributed to whoever wrote it, without re-prompting.

## How it works

mulchd builds on [mulch](https://github.com/jayminwest/mulch), a CLI that manages structured knowledge as JSONL records on disk. mulchd wraps it with an HTTP server that exposes eight MCP tools (`list_domains`, `read_records`, `write_record`, `edit_record`, `delete_record`, `search_records`, `get_recent`, `get_record_schema`) over the current MCP Streamable HTTP transport.

Knowledge is organized into domains (e.g. `architecture`, `conventions`, `ops`). Records have types — `decision`, `convention`, `pattern`, `failure`, `guide` — and carry attribution, classification, and optional supersession links so the team can track how thinking evolves over time.

An admin UI at `/admin` covers user and project management, a live record browser, and a full audit log with soft-delete and restore. A self-service `/connect` portal lets team members mint their own project-scoped tokens without admin involvement.

## Quick start

Requires Docker and Docker Compose.

```bash
git clone https://github.com/your-org/mulchd
cd mulchd
cp .env.example .env
```

Edit `.env` — at minimum set `MULCHD_SECRET_KEY` and `MULCHD_ADMIN_PASSWORD`:

```bash
# generate a secret key
python -c "import secrets; print(secrets.token_hex(32))"
```

Then:

```bash
docker compose up
```

Open `http://localhost:8000/admin`, log in with `admin` / the password you set, create a user and a project, then jump to [Connecting a client](#connecting-a-client).

## Production setup

Requirements: a VPS with Docker, a domain, and a DNS provider supported by Traefik's ACME challenge (the included config uses DigitalOcean).

**1. Configure environment files**

Copy the examples in `deploy/`:

```bash
cp deploy/mulchd.env.example deploy/mulchd.env
cp deploy/postgres.env.example deploy/postgres.env
cp deploy/traefik.env.example deploy/traefik.env
```

Fill in all values. For `mulchd.env`:

| Variable | Description |
|---|---|
| `MULCHD_SECRET_KEY` | 64-char hex string (`secrets.token_hex(32)`) |
| `MULCHD_ADMIN_PASSWORD` | Initial admin password — change after first login |

For `postgres.env`, pick any username, password, and database name. For `traefik.env`, add your DigitalOcean API token and ACME email.

**2. Set your hostname**

Edit `deploy/docker-compose.yml` and replace the Traefik host rule with your domain:

```yaml
- traefik.http.routers.mulchd.rule=Host(`mulchd.your-domain.com`)
```

**3. Deploy**

```bash
docker compose -f deploy/docker-compose.yml up -d
```

The entrypoint runs `aerich upgrade` before starting, so migrations apply automatically on each deploy. The admin UI will be at `https://mulchd.your-domain.com/admin`.

**4. Create your first user**

Log in to `/admin` and create a user account for each team member. Each user gets a global token on creation — this is shown once and used to log in to `/connect`.

## Connecting a client

mulchd works with any MCP-compatible client. The examples below are for Claude Code.

**1.** Log in to `/connect` with your global token. Pick a project, mint a project token, and copy the generated config snippets.

**2.** Add to your project's `.mcp.json`:

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

**3.** Add the token to `.claude/settings.local.json` (not committed):

```json
{
  "env": {
    "MULCHD_TOKEN_YOUR_PROJECT": "mlt_..."
  }
}
```

The `/connect` portal generates both snippets with the correct variable names — copy and paste rather than hand-editing.

## Roadmap

- **Automated alerting** — webhook or email notifications when structural audit events fire (cross-owner edits, foundational-record supersessions) rather than relying on manual log review
- **Seed script** — reproducible demo dataset for testing and screenshots
- **Claude Desktop snippets** — `/connect` already generates them; document the flow end-to-end
- **BM25 tuning** — expose search relevance knobs via config
- **OAuth / SSO** — replace global-token login with a standard provider

## Contributing

Issues and pull requests are welcome. For non-trivial changes, open an issue first to discuss the approach — especially anything touching the MCP tool interface or the audit trail, where backward compatibility and security posture matter. Please run `make format` and `make test` before submitting.

## Acknowledgements

mulchd builds on [mulch](https://github.com/jayminwest/mulch) by Jaymin West, which provides the JSONL knowledge store, BM25 search, and the `ml` CLI that mulchd shells out to for all record operations. mulch is MIT licensed.
