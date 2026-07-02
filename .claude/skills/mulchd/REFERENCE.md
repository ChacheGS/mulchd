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