# Invite links

Invite links let team members join a project themselves, without an admin creating an account for each person one by one.

## Creating a link

From a project's detail page in `/admin`, create an invite link with:

- **Role** — the `UserMembership` role (`reader`, `writer`, `admin`) granted to anyone who claims the link.
- **Max uses** (optional) — the link stops working once this many people have claimed it.
- **Expires in** (optional) — the link stops working after this much time has passed.
- **Allowed email domains** (optional) — one pattern per line. `company.com` matches that exact domain; `*.company.com` matches any subdomain. Leave blank to allow any email.

The link looks like `https://mulchd.your-domain.com/invite/<token>`. Share it with whoever should join the project.

## Claiming a link

Anyone who opens an invite link sees the project name and is asked to log in — via SSO (if configured) or a personal token, same as `/connect`. On successful login:

- If their email doesn't match the domain restriction, the claim is rejected with an opaque error (no detail on which restriction failed, to avoid leaking configuration).
- If the link is revoked, expired, or already at its max uses, the claim is rejected the same way.
- Otherwise they're added to the project with the link's role, and the link's use count increments.
- If they're already a member of the project, the claim is a silent no-op — the use count does not increment again.

Claiming is atomic under concurrent use: two people racing to claim the last remaining use of a link can't both succeed.

## Revoking a link

Revoke a link from the same project detail page. Revoked links can't be un-revoked — create a new one instead.

## Attribution and auditing

Every invite link records which admin created it. Creation and revocation both appear in the [instance activity log](admin-rbac.md#instance-activity-log).
