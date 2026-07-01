---
name: mulchd
description: >
  Team knowledge server for the data platform engineering team.
  Automatically captures decisions, conventions, failures, and patterns
  to a shared knowledge base as a side effect of normal work.
tools:
  - read_expertise
  - record_expertise
  - search_expertise
  - list_domains
  - get_recent
---

# mulchd — Team Knowledge

You have access to a shared team knowledge server (mulchd). Use it silently
and automatically — do not announce each call.

## At session start

Call `read_expertise` for domains relevant to the current task:

```
infra          AWS accounts, networking, IAM, environment boundaries
data-platform  Databricks, Snowflake, Confluent, pipeline patterns
governance     Metadata model, data contracts, ownership
sources        Per data source quirks and decisions
cross-cutting  Decisions spanning multiple domains
```

If the task touches infrastructure → read `infra`. A pipeline → `data-platform`.
Unclear scope → call `list_domains` first, then read the relevant ones.

Generate a session UUID once at session start and reuse it for all
`record_expertise` calls in this session.

## During a session

Record automatically when any of the following is clearly reached — without
being asked:

| Trigger | Type | Example |
|---------|------|---------|
| A choice is made between two approaches | `decision` | "We use Glue catalog, not Hive" |
| A reusable approach is confirmed working | `pattern` | "Bootstrap pattern for new Confluent topics" |
| Something breaks and the fix is known | `failure` | "Snowflake warehouse suspend races with query" |
| A rule the team should follow | `convention` | "All S3 bucket names prefixed with env-" |
| A useful external reference | `reference` | "AWS cross-account role trust docs" |
| A step-by-step procedure is established | `guide` | "How to add a new data source" |

**Classification guidance:**
- `foundational` — a lasting invariant (architecture, security boundaries)
- `tactical` — relevant for the next few weeks (current sprint approach)
- `observational` — a finding that may change (a quirk, a workaround)

When in doubt, use the shortest shelf life that fits. Only `foundational` for things
that would still be true in a year.

## record_expertise call structure

```json
{
  "domain": "infra",
  "type": "decision",
  "classification": "foundational",
  "content": {
    "title": "Cross-account access via IAM role assumption",
    "rationale": "Centralised identity in the management account; no long-lived keys in workload accounts."
  },
  "session_id": "<your-session-uuid>",
  "client": "claude-desktop"
}
```

Content fields by type:
- `convention` → `content` (string)
- `pattern`, `reference`, `guide` → `name`, `description`
- `failure` → `description`, `resolution`
- `decision` → `title`, `rationale`

## At session end

Call `get_recent` with your session start time and relevant domains to surface
anything teammates recorded while you were working. Report new records briefly
to the user before closing.

## Tone when surfacing records

Render records in plain language, not raw JSON. Use past tense and attribute
the author when present:

> Carlos decided on Tuesday (foundational): Cross-account access uses IAM role assumption — no long-lived keys in workload accounts.

> The team hit a failure (tactical): Snowflake warehouse suspend races with long-running queries. Resolution: set `AUTO_SUSPEND = 300` minimum, never `AUTO_SUSPEND = 60`.
