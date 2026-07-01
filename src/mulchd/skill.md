# mulchd — Team Knowledge for Claude

mulchd is a self-hosted MCP server that stores and retrieves team expertise per project.
Knowledge is scoped to the project your token was minted for — other projects are invisible.
All team members with access to the same project share a common knowledge pool.

---

## First-time setup

You need two things: the **server URL** and your **global token** (issued by the admin when
your account was created). Everything else is self-service.

Run the following steps using whatever HTTP tool is available (curl, Bash, WebFetch):

**1. List your accessible projects**

```bash
curl -s https://SERVER_URL/api/me/projects \
  -H "Authorization: Bearer GLOBAL_TOKEN"
# → [{"org": {"slug": "acme", ...}, "project": {"slug": "infra", ...}, "role": "writer"}, ...]
```

**2. Mint a project-scoped token** (one per project; multiple per project is fine for different machines)

```bash
curl -s -X POST https://SERVER_URL/api/projects/ORG/PROJECT/tokens \
  -H "Authorization: Bearer GLOBAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"label": "claude-code-laptop"}'
# → {"id": 1, "token": "PROJECT_TOKEN", "label": "claude-code-laptop", ...}
```

The raw token is shown once. Copy it.

**3. Write `.claude/settings.local.json`** in the project root (gitignored by default):

```json
{
  "mcpServers": {
    "mulchd": {
      "type": "sse",
      "url": "https://SERVER_URL/sse",
      "headers": {
        "Authorization": "Bearer PROJECT_TOKEN"
      }
    }
  }
}
```

Restart Claude Code. The mulchd tools are now active for this project.

> **Claude Desktop** — same token, different config file:
> Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`
> Windows: `%APPDATA%\Claude\claude_desktop_config.json`
> Desktop config is global; name the entry to identify the project (e.g. `mulchd-acme-infra`).

---

## Session workflow

### Session start

Load expertise for the domains relevant to your task. If you don't know what domains exist,
call `list_domains` first, then `read_expertise`.

```
list_domains()
read_expertise(domains=["infra", "data-platform"])
```

### During the session

Record proactively — without being asked. Triggers:

- A decision was made or confirmed → `decision`
- A convention was established or violated and corrected → `convention`
- Something broke and was fixed → `failure`
- A reusable solution or code shape emerged → `pattern`
- You need to find relevant past context → `search_expertise`

### Session end

Fetch recent changes to catch expertise your teammates recorded while you were working:

```
get_recent(since="<ISO timestamp from session start>", domains=["infra"])
```

---

## Record type schemas

**This is the most important section.** Each call to `record_expertise` requires a `content`
object whose keys depend on `type`. Wrong or missing fields cause a validation error from the
mulch backend. Use the table and examples below — do not guess field names.

### Required fields per type

| `type` | required fields in `content` | optional fields in `content` |
|---|---|---|
| `convention` | `content` (string) | — |
| `decision` | `title` (string), `rationale` (string) | `date` (string) |
| `failure` | `description` (string), `resolution` (string) | — |
| `pattern` | `name` (string), `description` (string) | `files` (array of strings) |
| `reference` | `name` (string), `description` (string) | `files` (array of strings) |
| `guide` | `name` (string), `description` (string) | — |

### Complete examples

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

---

## Classification

| value | use when |
|---|---|
| `foundational` | Core constraints that shape everything else: architecture choices, key dependencies, non-negotiables. Changes rarely and deliberately. |
| `tactical` | Day-to-day conventions, implementation patterns, tooling choices. Reviewed and updated as the project evolves. |
| `observational` | Things noticed in passing — not yet a convention, not yet a decision. May be promoted later. |

Default to `tactical` when unsure.

---

## Tool reference

| tool | call it when |
|---|---|
| `list_domains` | You don't know what domains exist for the project |
| `read_expertise` | Loading context at session start, or before working in a domain |
| `record_expertise` | A decision, convention, failure, pattern, reference, or guide should be captured |
| `search_expertise` | You need to find specific past context by keyword |
| `get_recent` | End of session — surfacing what teammates recorded while you were working |

### `record_expertise` optional base fields

Beyond the type-specific `content` fields, you may also include in `content`:

- `tags` — array of strings, for cross-cutting labels
- `files` — array of repo-relative file paths (for `pattern` and `reference`)
- `relates_to` — array of record IDs (`mx-xxxxxx`) this record is related to
- `supersedes` — array of record IDs this record replaces
