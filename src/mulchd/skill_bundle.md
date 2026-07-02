# mulchd skill bundle — v{{ skill_version }}

You (Claude) have just fetched the mulchd team-knowledge skill. This bundle contains
three files and instructions for installing them. **Follow the section matching the
client you are running in, then confirm to the user what was installed.**

---

## If you are Claude Code (or any client with filesystem access)

Materialize the skill folder inside the current project:

1. Create the directory `.claude/skills/mulchd/`.
2. Populate it with the three files. Preferred: fetch each one fresh —

   ```
   GET {{ mulchd_url }}/skill/SKILL.md
   GET {{ mulchd_url }}/skill/SETUP.md
   GET {{ mulchd_url }}/skill/REFERENCE.md
   ```

   Fallback (endpoints unreachable but you have this bundle): split this document on the
   `<!-- mulchd:file ... -->` / `<!-- mulchd:endfile -->` markers below and write each
   section to its filename verbatim, markers excluded.
3. If the project has a `CLAUDE.md`, append the pointer block from SETUP.md step 4
   (create `CLAUDE.md` with it otherwise).
4. If the project is a git repo, tell the user these files are safe to commit — they
   contain no tokens. If it is not a git repo, that's fine; the folder works locally.
5. If the mulchd MCP server is not yet connected (`/mcp` doesn't list it), walk the user
   through SETUP.md before doing anything else.

## If you are Claude Desktop (no filesystem / no skills folder)

There is nothing to write to disk. Instead:

1. Tell the user to paste the contents of the `SKILL.md` section below (frontmatter
   excluded) into this project's custom instructions field.
2. If the mulchd MCP server is not yet configured, walk them through the Desktop parts
   of the `SETUP.md` section below.

---

<!-- mulchd:file SKILL.md -->
---
name: mulchd
description: >
  Team knowledge for this project via the mulchd MCP server. Use at the start of every
  session to load team expertise, during sessions to proactively record decisions,
  conventions, failures, and patterns, and at session end to surface teammates' recent
  records. If the mulchd MCP server is not connected or this is a new machine, read
  SETUP.md in this folder first.
---

# mulchd — Session Workflow

> Skill version: {{ skill_version }} · Canonical source: {{ mulchd_url }}/skill
> First time on this machine or MCP server not connected? → read `SETUP.md`.
> Unsure which fields a record type needs? → call `get_record_schema` or read `REFERENCE.md`.

mulchd stores shared team expertise, scoped to this project. Everything you record is
visible to the whole team, attributed to the user, and persists indefinitely.

## Session start

1. **Note the current UTC timestamp** — needed for `get_recent` at session end.
2. `list_domains()` — see what knowledge domains exist.
3. `read_expertise(domains=[...])` — load the domains relevant to the current task.

## During the session — record proactively

Record **without being asked** whenever:

- A decision is made or confirmed → `decision`
- A convention is established or corrected → `convention`
- Something breaks and gets fixed → `failure`
- A reusable solution or code shape emerges → `pattern`

**Before every write, search first:** `search_expertise(query="<topic keywords>")`

- Equivalent record exists → don't duplicate. Skip, or `edit_record` (own records), or
  write a new record with `supersedes` if this replaces it.
- No match → record it.

**Never record:**

- Secrets, credentials, account IDs, or client-identifying data — under no circumstances
- Trivial details or anything reversible in minutes
- Speculation or options discussed but not settled
- Restatements of existing records

**Keep it tight.** Rationale in 2–4 sentences: the decision and the *why*, not the whole
deliberation.

## Conflicting records

1. Prefer `foundational` over `tactical` over `observational`.
2. Within a tier, prefer the newer record.
3. Two live records genuinely contradict → **flag it to the user** and propose a
   superseding record. Never silently pick one.

## If mulchd is unreachable

Don't stall or retry endlessly. Continue the work, keep a list of the records you would
have written, and show it to the user at session end for later recording.

## Session end

```
get_recent(since="<session start UTC timestamp>", domains=[...])
```

Relay anything relevant: "While we worked, Alice recorded a decision on Snowflake schema
naming — it affects what we just did."

## Tool reference

| tool | call it when |
|---|---|
| `list_domains` | You don't know what domains exist |
| `read_expertise` | Session start, or before working in a domain |
| `search_expertise` | Before any write, and to find past context by keyword |
| `record_expertise` | Capturing a record — **after** search found no equivalent |
| `get_record_schema` | Unsure which fields a type requires — call before writing |
| `edit_record` | Updating an existing record (writers: own only; admins: any) |
| `delete_record` | Removing an obsolete record (same ownership rules) |
| `get_recent` | Session end — what teammates recorded meanwhile |

## Classification (quick guide)

`foundational` — core constraints, changes rarely · `tactical` — day-to-day conventions
and patterns (default when unsure) · `observational` — noticed in passing, may be
promoted later. Full guidance and record schemas: `REFERENCE.md`.
<!-- mulchd:endfile -->

<!-- mulchd:file SETUP.md -->
# mulchd — Setup

Read this once per machine, or when joining a new project. Day-to-day usage is in
`SKILL.md`.

Works with **Claude Code** (macOS / Linux / Windows) and **Claude Desktop**
(macOS / Windows).

---

## Security rules

1. **Never send a token over plain HTTP** to a non-localhost server. `localhost` is for
   local testing only; the team server is always HTTPS.
2. **Never put a raw token on a command line.** Command lines end up in shell history and
   conversation transcripts. Source tokens from the credentials file and use variable
   expansion.
3. **Never commit a raw token to git.** `.mcp.json` uses env var expansion and is safe to
   commit; the credentials file and any `.env` holding tokens are never committed.
4. **Never record secrets into mulchd** — no credentials, API keys, account IDs, or
   client-identifying data. Records are team-visible and permanent.
5. Token possibly leaked (lost laptop, pasted into a transcript, committed by accident)?
   Revoke immediately — see **Token lifecycle**.

---

## Credentials file

All tokens live in one file per machine, outside any repo.

**macOS / Linux:** `~/.config/mulchd/credentials`

```bash
mkdir -p ~/.config/mulchd && chmod 700 ~/.config/mulchd
cat > ~/.config/mulchd/credentials <<'EOF'
export MULCHD_URL="{{ mulchd_url }}"
export MULCHD_GLOBAL_TOKEN="glb_..."
# One line per project token:
export {{ token_env_var }}="prj_..."
EOF
chmod 600 ~/.config/mulchd/credentials
```

Load: `source ~/.config/mulchd/credentials`

**Windows:** `%USERPROFILE%\.mulchd\credentials.ps1`

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.mulchd" | Out-Null
@'
$env:MULCHD_URL = "{{ mulchd_url }}"
$env:MULCHD_GLOBAL_TOKEN = "glb_..."
$env:{{ token_env_var }} = "prj_..."
'@ | Set-Content "$env:USERPROFILE\.mulchd\credentials.ps1"
```

Load: `. $env:USERPROFILE\.mulchd\credentials.ps1`

The **global token** is issued once by the admin with your account. Keep it here
permanently — it's needed again for every new project or machine. **Project tokens** are
self-service (below), one per project per machine, so a single machine can be revoked
without re-onboarding you.

---

## Project setup (once per project per machine)

Use whatever HTTP tool is available (curl, PowerShell `Invoke-RestMethod`, WebFetch).

**1. Load credentials, list your accessible projects**

```bash
source ~/.config/mulchd/credentials   # Windows: . $env:USERPROFILE\.mulchd\credentials.ps1
curl -s "$MULCHD_URL/api/me/projects" \
  -H "Authorization: Bearer $MULCHD_GLOBAL_TOKEN"
```

**2. Mint a project token**, labelled with the machine so it can be revoked individually:

```bash
curl -s -X POST "$MULCHD_URL/api/projects/{{ org }}/{{ project }}/tokens" \
  -H "Authorization: Bearer $MULCHD_GLOBAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"label\": \"claude-code-$(hostname)\"}"
```

The raw token is shown **once**. Add it to the credentials file immediately as
`{{ token_env_var }}` and paste it nowhere else.

**3. Register the MCP server**

### Claude Code — `.mcp.json` in the project root

Env var expansion makes this file **safe to commit** where a repo exists (and it should
be — it onboards the next teammate for free):

```json
{
  "mcpServers": {
    "mulchd": {
      "type": "http",
      "url": "{{ mulchd_url }}/mcp",
      "headers": {
        "Authorization": "Bearer {{ token_env_var_ref }}"
      }
    }
  }
}
```

The env vars must exist in the environment Claude Code launches from: source the
credentials file in your shell profile (`.bashrc` / `.zshrc` / PowerShell `$PROFILE`), or
use a gitignored `.env` if your launcher supports it.

Approve the server in `.claude/settings.local.json` (gitignored — do not commit):

```json
{
  "enabledMcpjsonServers": ["mulchd"]
}
```

Restart Claude Code, run `/mcp` — `mulchd` should show green. If disconnected, verify the
env vars are set in the launching shell (`echo $MULCHD_URL`).

### Claude Desktop — global config file

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Desktop does not expand env vars in its config, so the raw token goes in the file. That's
acceptable — this file is per-user, outside any repo, never committed — but treat it like
the credentials file: no screenshots, no pasting into chats. Name entries per project,
since the config is global:

```json
{
  "mcpServers": {
    "mulchd-{{ org }}-{{ project }}": {
      "type": "http",
      "url": "{{ mulchd_url }}/mcp",
      "headers": {
        "Authorization": "Bearer prj_..."
      }
    }
  }
}
```

**4. Wire up session instructions**

### Claude Code — `CLAUDE.md`

A pointer only, so instructions can't drift from the skill:

```markdown
## mulchd — Team Knowledge

This project uses mulchd. Follow the session workflow in
`.claude/skills/mulchd/SKILL.md` (session start → proactive recording → session end).
```

### Claude Desktop

No `CLAUDE.md` and no skills folder. Paste the contents of `SKILL.md` (minus the
frontmatter) into the project's custom instructions field in the Desktop UI.

**5. Persist the skill for the next person**

- Working in a git repo → commit `.claude/skills/mulchd/`, `.mcp.json`, and the
  `CLAUDE.md` pointer. They contain no tokens.
- No repo (Desktop users, ad-hoc folders) → nothing to commit; the skill is always
  re-fetchable from `{{ mulchd_url }}/skill`, which is the canonical source.

---

## Token lifecycle

- **Revoke a machine's token:** web UI → project → tokens → revoke, or
  `DELETE $MULCHD_URL/api/projects/{{ org }}/{{ project }}/tokens/ID` with the global token.
  Per-machine tokens mean revoking one machine doesn't touch your others.
- **Rotate the global token:** admin action in the web UI; update the credentials file
  afterwards.
- **Lost laptop / leaked token:** revoke that machine's project tokens immediately; ask
  the admin to rotate your global token if it lived on that machine too.

---

## Keeping the skill up to date

The canonical skill is served by the mulchd server at `{{ mulchd_url }}/skill` (bundle) and
`{{ mulchd_url }}/skill/<FILE>` (individual files), always at the server's current version.
Vendored copies carry their version in `SKILL.md`; re-fetch when the server version is
newer.
<!-- mulchd:endfile -->

<!-- mulchd:file REFERENCE.md -->
# mulchd — Record Reference

Read this when about to write a record and unsure of the fields. The live source of truth
is the `get_record_schema` tool — this file may lag behind the server.

Each `record_expertise` call takes a `content` object whose keys depend on `type`. Wrong
or missing fields cause a validation error from the mulch backend. Do not guess field
names.

## Required fields per type

| `type` | required fields in `content` | optional fields in `content` |
|---|---|---|
| `convention` | `content` (string) | — |
| `decision` | `title` (string), `rationale` (string) | `date` (string) |
| `failure` | `description` (string), `resolution` (string) | — |
| `pattern` | `name` (string), `description` (string) | `files` (array of strings) |
| `reference` | `name` (string), `description` (string) | `files` (array of strings) |
| `guide` | `name` (string), `description` (string) | — |

## Optional base fields (any type)

- `tags` — array of strings, for cross-cutting labels
- `files` — array of repo-relative file paths (for `pattern` and `reference`)
- `relates_to` — array of record IDs (`mx-xxxxxx`) this record relates to
- `supersedes` — array of record IDs this record replaces

## Classification

| value | use when |
|---|---|
| `foundational` | Core constraints that shape everything else: architecture choices, key dependencies, non-negotiables. Changes rarely and deliberately. |
| `tactical` | Day-to-day conventions, implementation patterns, tooling choices. Reviewed and updated as the project evolves. **Default when unsure.** |
| `observational` | Noticed in passing — not yet a convention or decision. May be promoted later. |

## Complete examples

**convention** — a rule the team follows:

```json
{
  "domain": "infra",
  "type": "convention",
  "classification": "tactical",
  "content": {
    "content": "All S3 buckets must have versioning and server-side encryption enabled at creation."
  }
}
```

**decision** — a choice made, with the reasoning that justifies it:

```json
{
  "domain": "infra",
  "type": "decision",
  "classification": "foundational",
  "content": {
    "title": "Use Terraform for all infrastructure",
    "rationale": "Reproducible environments, GitOps workflow, state in S3. Pulumi was evaluated but Terraform's provider ecosystem is wider for our AWS footprint."
  }
}
```

**failure** — something that broke, and how to prevent or fix it:

```json
{
  "domain": "infra",
  "type": "failure",
  "classification": "tactical",
  "content": {
    "description": "NAT gateway quota exhaustion caused a prod outage during a traffic spike.",
    "resolution": "Request quota increase before provisioning new VPCs. Add a quota check step to the environment runbook."
  }
}
```

**pattern** — a reusable solution, structure, or code shape:

```json
{
  "domain": "data-platform",
  "type": "pattern",
  "classification": "tactical",
  "content": {
    "name": "idempotent-snowflake-upsert",
    "description": "Use MERGE INTO with a deterministic surrogate key for Snowflake loads. Survives retries without duplicates. Key is SHA256 of (source_system, entity_id, event_timestamp).",
    "files": ["pipelines/snowflake_loader.py", "pipelines/utils/keys.py"]
  }
}
```

**reference** — a pointer to a document, template, or external resource:

```json
{
  "domain": "governance",
  "type": "reference",
  "classification": "foundational",
  "content": {
    "name": "Data contract template",
    "description": "Canonical YAML template all new data sources must register. Defines SLA, ownership, and schema versioning expectations.",
    "files": ["contracts/template.yaml"]
  }
}
```

**guide** — a how-to for a team process:

```json
{
  "domain": "infra",
  "type": "guide",
  "classification": "tactical",
  "content": {
    "name": "Rotating RDS credentials",
    "description": "Run ops/rotate-creds.sh, then update the SSM Parameter Store entry. Never commit credentials. Verify rotation succeeded in CloudWatch Logs before closing the ticket."
  }
}
```
<!-- mulchd:endfile -->
