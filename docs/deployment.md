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

To enable GitHub or OIDC sign-in on the `/connect` portal, uncomment and fill in the relevant OAuth vars in `deploy/mulchd.env` (see `mulchd.env.example`). Users must have their email set in the admin before their first SSO login — the server matches the provider's verified email to `User.email` to link the identity automatically.
