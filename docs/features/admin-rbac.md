# Admin access and the activity log

## Admin access (SUPERADMIN grants)

There's no single shared admin password. Admin access is a per-user grant (`AdminGrant`, role `SUPERADMIN`), so any number of people can hold it independently, and any admin can grant or revoke it for another user from that user's detail page in `/admin`.

A few rules keep this safe:

- **Bootstrapping** — see the README's "Bootstrap the first admin" step for how the very first grant gets created (via OAuth login matching `MULCHD_BOOTSTRAP_ADMIN_EMAIL`, or the CLI fallback). Both paths refuse to run again once any admin grant exists.
- **Last-admin guard** — you can't revoke the sole remaining admin's access, and you can't deactivate their account either. Self-revoke is allowed as long as another admin remains — a clean handoff, not a way to lock everyone out.
- **Soft-revoke** — revoking a grant sets `revoked_at`/`revoked_by` rather than deleting the row, so the `AdminGrant` table is itself a durable record of who's had admin access and when it changed.
- **Authentication is unchanged** — admins log in through the same `/connect` OAuth/token flow as any team member. Holding an active grant is what makes `/admin` accessible, not a separate login.

## Instance activity log

`/admin/activity` records account- and access-level events across the whole instance — the kind of thing an admin needs to answer "who did this and when," separate from the per-project record audit log at `/admin/audit` (writes/edits/deletes of individual knowledge records, with restore).

Logged events: admin grant/revoke, project membership added/removed (including via invite-link claims), organization/project created, invite link created/revoked, user created/deactivated, global token reset, first login, and OAuth identity linked.

Each entry shows the actor, a human-readable description, and a timestamp, filterable by category, actor, or project. Entries are never deleted or edited — if you need to correct something, it happens via a new action that logs its own entry, not by rewriting history.
