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

> Skill version: 2.2 · Canonical source: http://localhost:8000/skill
> First time on this machine or MCP server not connected? → read `SETUP.md`.
> Unsure which fields a record type needs? → call `get_record_schema` or read `REFERENCE.md`.

mulchd stores shared team expertise, scoped to this project. Everything you record is
visible to the whole team, attributed to the user, and persists indefinitely.

## Session start

1. **Note the current UTC timestamp** — needed for `get_recent` at session end.
2. `list_domains()` — see what domains exist and when they were last updated.
3. `read_expertise(domains=[...])` — pass all domains returned above, or just the ones
   relevant to the current task. When in doubt, load everything: records are short.
4. **Check skill version**: compare the version in this file (`2.2`) against
   `GET http://localhost:8000/health` → `skill_version`. If they differ, re-fetch the skill
   files from `http://localhost:8000/skill/SKILL.md` etc. before continuing.

## During the session — record proactively

Record **without being asked** whenever:

- A decision is made or confirmed → `decision`
- A convention is established or corrected → `convention`
- Something breaks and gets fixed → `failure`
- A reusable solution or code shape emerges → `pattern`

**Before writing to an existing domain, search first:**
`search_expertise(query="<topic keywords>")`

- Equivalent record exists → don't duplicate. Skip, or `edit_record` (own records), or
  write a new record with `supersedes` if this replaces it.
- No match → record it.
- **First write to a brand-new domain** → skip the search, there's nothing there yet.

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