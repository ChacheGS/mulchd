# Production deployment

Requirements: a VPS with Docker, a domain, and a DNS provider supported by Traefik's ACME challenge (the included config uses DigitalOcean).

## 1. Configure environment files

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
| `mulchd.env` | `MULCHD_BASE_URL` | Public `https://` URL, e.g. `https://mulchd.your-domain.com` — should match `MULCHD_HOSTNAME` below. Required for MCP OAuth (step 6) to work; without it, mulchd falls back to an insecure default URL that the OAuth routes refuse to register under |
| `.env` | `MULCHD_HOSTNAME` | Public hostname, e.g. `mulchd.your-domain.com` |

## 2. Deploy

```bash
docker compose -f deploy/docker-compose.yml up -d
```

Migrations run automatically on each deploy. The admin UI will be at `https://mulchd.your-domain.com/admin`.

## 3. Bootstrap the first admin

There's no default admin account — the first `SUPERADMIN` grant has to come from somewhere. If you're using SSO (see step 5 below), set `MULCHD_BOOTSTRAP_ADMIN_EMAIL` and log in via `/connect`; the grant happens automatically on that first login. If you're not using SSO, run this instead:

```bash
make bootstrap-admin USERNAME=yourname DISPLAY_NAME="Your Name" EMAIL=you@example.com
```

This creates the account and prints its global token once — save it, then log in to `/connect` with it. Either path refuses to run again once any admin exists, so it's safe to leave configured. See [admin access and the activity log](features/admin-rbac.md) for how admin grants work once you have more than one admin.

## 4. Create users

Log in to `/admin` and create an account for each team member. Each user gets a global token on creation — shown once, used to log in to `/connect`. Alternatively, use an [invite link](features/invite-links.md) to let people join a project themselves.

## 5. Configure SSO (optional)

To enable GitHub or OIDC sign-in on the `/connect` portal, uncomment and fill in the relevant OAuth vars in `deploy/mulchd.env` (see `mulchd.env.example`). Any number of OIDC providers can be configured at once — each gets its own `MULCHD_OIDC_<PROVIDER>_*` env var prefix. Users must have their email set in the admin before their first SSO login — the server matches the provider's verified email to `User.email` to link the identity automatically.

## 6. MCP OAuth for clients (on by default)

MCP clients that support OAuth (Claude Desktop, MCP Inspector) connect directly to `https://mulchd.your-domain.com/mcp` without a manually-pasted token, provided `MULCHD_BASE_URL` (step 1) is set — the OAuth authorization-server routes silently don't register without it, and mulchd logs a startup warning if they don't. Set `MULCHD_MCP_OAUTH_ENABLED=false` in `mulchd.env` to disable this and always require the manual project-token flow instead.
