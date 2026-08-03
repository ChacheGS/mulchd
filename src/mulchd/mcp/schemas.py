"""Static MCP tool schemas and record-type metadata for tier2.

Pure data — no logic, no dependency on anything else in the mcp package.
Separates "what the tools look like" from "how a tool call is handled",
which is what the rest of tier2.py does.
"""

from mcp.types import Tool, ToolAnnotations

_RECORD_FIELD_KEYS = frozenset(
    {
        "content",
        "title",
        "rationale",
        "description",
        "resolution",
        "name",
        "files",
        "relates_to",
        "supersedes",
        "date",
        "evidence",
    }
)

_CLASSIFICATION_PROPERTY = {
    "type": "string",
    "enum": ["foundational", "tactical", "observational"],
    "description": "foundational: core conventions/decisions that rarely change; tactical: current approach, may evolve; observational: useful context, specific to a situation or moment",
}

_EVIDENCE_STRING_OR_ARRAY = {
    "oneOf": [
        {"type": "string"},
        {"type": "array", "items": {"type": "string"}},
    ],
}

_RELATED_RECORD_PROPERTIES = {
    "files": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Related file paths",
    },
    "relates_to": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Related record IDs",
    },
    "supersedes": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Record IDs this record replaces",
    },
}

# Evidence can only be set at record-creation time via write_* — not editable
# later via edit_record — so this is spread only into the six write_* tool
# schemas below, never into _RELATED_RECORD_PROPERTIES (which edit_record also
# uses).
_EVIDENCE_PROPERTIES = {
    "evidence": {
        "type": "object",
        "description": (
            "Supporting evidence for this record. All fields optional — set "
            "only what applies. Each field accepts either a single value or "
            "an array of values (e.g. multiple PRs or tickets); arrays are "
            "joined into one string before being persisted."
        ),
        "properties": {
            "commit": {**_EVIDENCE_STRING_OR_ARRAY, "description": "Git commit hash(es)"},
            "date": {"type": "string", "description": "ISO 8601 date the evidence applies to"},
            "issue": {**_EVIDENCE_STRING_OR_ARRAY, "description": "Generic issue reference(s)"},
            "file": {**_EVIDENCE_STRING_OR_ARRAY, "description": "Specific file path(s) this evidence points to"},
            "bead": {**_EVIDENCE_STRING_OR_ARRAY, "description": "Bead tracker ID(s)"},
            "seeds": {**_EVIDENCE_STRING_OR_ARRAY, "description": "Seeds tracker issue ID(s)"},
            "gh": {**_EVIDENCE_STRING_OR_ARRAY, "description": "GitHub issue or PR reference(s)"},
            "linear": {**_EVIDENCE_STRING_OR_ARRAY, "description": "Linear ticket reference(s)"},
        },
        # ml's own evidence schema is additionalProperties: false — match that
        # here so an unrecognized key is rejected by the MCP SDK's jsonschema
        # validation (which runs before the handler, see call_tool's default
        # validate_input=True) instead of surfacing later as an ml write failure.
        "additionalProperties": False,
    },
}

_WRITE_TOOLS = [
    Tool(
        name="write_convention",
        description=(
            "Record a convention that's been established or corrected — without being asked. "
            "Writing to a domain that does not exist will create it automatically."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "classification": _CLASSIFICATION_PROPERTY,
                "content": {"type": "string", "description": "Body text of the convention."},
                **_RELATED_RECORD_PROPERTIES,
                **_EVIDENCE_PROPERTIES,
            },
            "required": ["domain", "classification", "content"],
        },
        annotations=ToolAnnotations(destructiveHint=True),
    ),
    Tool(
        name="write_decision",
        description=(
            "Record a decision that's been made or confirmed — without being asked. "
            "Writing to a domain that does not exist will create it automatically."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "classification": _CLASSIFICATION_PROPERTY,
                "title": {"type": "string", "description": "Short title for the decision."},
                "rationale": {"type": "string", "description": "The decision and why it was made."},
                "date": {
                    "type": "string",
                    "description": "Date the decision was made (ISO 8601); defaults to recorded_at.",
                },
                **_RELATED_RECORD_PROPERTIES,
                **_EVIDENCE_PROPERTIES,
            },
            "required": ["domain", "classification", "title", "rationale"],
        },
        annotations=ToolAnnotations(destructiveHint=True),
    ),
    Tool(
        name="write_failure",
        description=(
            "Record something that broke and how it got fixed — without being asked. "
            "Writing to a domain that does not exist will create it automatically."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "classification": _CLASSIFICATION_PROPERTY,
                "description": {"type": "string", "description": "What broke."},
                "resolution": {"type": "string", "description": "How it was fixed."},
                **_RELATED_RECORD_PROPERTIES,
                **_EVIDENCE_PROPERTIES,
            },
            "required": ["domain", "classification", "description", "resolution"],
        },
        annotations=ToolAnnotations(destructiveHint=True),
    ),
    Tool(
        name="write_pattern",
        description=(
            "Record a reusable solution or code shape that emerged — without being asked. "
            "Writing to a domain that does not exist will create it automatically."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "classification": _CLASSIFICATION_PROPERTY,
                "name": {"type": "string", "description": "Short name for the pattern."},
                "description": {"type": "string", "description": "What the pattern is and how to use it."},
                **_RELATED_RECORD_PROPERTIES,
                **_EVIDENCE_PROPERTIES,
            },
            "required": ["domain", "classification", "name", "description"],
        },
        annotations=ToolAnnotations(destructiveHint=True),
    ),
    Tool(
        name="write_reference",
        description=(
            "Record a reference — a pointer to external info worth remembering — without "
            "being asked. Writing to a domain that does not exist will create it automatically."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "classification": _CLASSIFICATION_PROPERTY,
                "name": {"type": "string", "description": "Short name for the reference."},
                "description": {"type": "string", "description": "What it points to and why it matters."},
                **_RELATED_RECORD_PROPERTIES,
                **_EVIDENCE_PROPERTIES,
            },
            "required": ["domain", "classification", "name", "description"],
        },
        annotations=ToolAnnotations(destructiveHint=True),
    ),
    Tool(
        name="write_guide",
        description=(
            "Record a how-to guide — without being asked. "
            "Writing to a domain that does not exist will create it automatically."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "classification": _CLASSIFICATION_PROPERTY,
                "name": {"type": "string", "description": "Short name for the guide."},
                "description": {"type": "string", "description": "The guide's steps or content."},
                **_RELATED_RECORD_PROPERTIES,
                **_EVIDENCE_PROPERTIES,
            },
            "required": ["domain", "classification", "name", "description"],
        },
        annotations=ToolAnnotations(destructiveHint=True),
    ),
]

TIER2_TOOLS = [
    Tool(
        name="read_records",
        description=(
            "Load team records. Omit `since` at session start to load context for "
            "the current task (oldest first). Pass `since` to see what changed — at "
            "session end, or when a notification suggests a domain moved — and results "
            "come back newest first, grouped by the session that wrote them."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Domain names to read from. Defaults to all domains.",
                },
                "since": {
                    "type": "string",
                    "description": (
                        "ISO 8601 timestamp. Returns only records recorded after this "
                        "time, newest first. Omit to load records oldest first instead."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Max records to return across all domains.",
                },
                "cursor": {
                    "type": "string",
                    "description": "Pass next_cursor from the previous response verbatim. Omit for the first page.",
                },
                "type": {
                    "type": "string",
                    "enum": ["convention", "decision", "failure", "pattern", "reference", "guide"],
                    "description": "Only return records of this type.",
                },
                "classification": _CLASSIFICATION_PROPERTY,
                "file": {
                    "type": "string",
                    "description": "Only return records whose related files include this path (case-insensitive substring match).",
                },
                "outcome_status": {
                    "type": "string",
                    "enum": ["success", "failure", "partial"],
                    "description": "Only return records with at least one outcome of this status.",
                },
            },
        },
        outputSchema={
            "type": "object",
            "properties": {
                "records": {"type": "array", "items": {"type": "object"}},
                "truncated": {"type": "boolean"},
                "next_cursor": {
                    "type": ["string", "null"],
                    "description": "Pass as cursor on the next call to fetch the following page. Null when no more records remain.",
                },
                "unknown_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Requested domains not found in this project.",
                },
                "cross_domain_hints": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Records superseded by records in domains outside the current read scope. Read those domains for the full picture.",
                },
            },
            "required": ["records", "truncated"],
        },
        annotations=ToolAnnotations(readOnlyHint=True),
    ),
    *_WRITE_TOOLS,
    Tool(
        name="search_records",
        description=(
            "Search records by query, optionally filtered by domain or owner. "
            "Results are relevance-ranked within each matching domain, capped "
            "to `limit` per domain — there is no single relevance ranking "
            "across multiple domains, so this is not a global top-N."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Limit search to these domains. Defaults to all domains.",
                },
                "owner": {
                    "type": "string",
                    "description": "Filter to records written by this username.",
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Max results per matching domain (not a global total). "
                        "Defaults to 20."
                    ),
                },
            },
            "required": ["query"],
        },
        outputSchema={
            "type": "object",
            "properties": {
                "records": {"type": "array", "items": {"type": "object"}},
                "truncated": {"type": "boolean"},
            },
            "required": ["records", "truncated"],
        },
        annotations=ToolAnnotations(readOnlyHint=True),
    ),
    Tool(
        name="list_domains",
        description="List available domains with record counts and last-updated timestamps.",
        inputSchema={"type": "object", "properties": {}},
        outputSchema={
            "type": "object",
            "properties": {
                "server_time": {"type": "string"},
                "recent_hint": {
                    "type": "string",
                    "description": "Reminder to call read_records(since=server_time) at session end.",
                },
                "language": {
                    "type": "string",
                    "description": "Knowledge base language code, if set.",
                },
                "domains": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "record_count": {"type": "integer"},
                            "last_updated": {"type": ["string", "null"]},
                            "uri": {
                                "type": "string",
                                "description": "Resource URI for read_records / subscribe.",
                            },
                        },
                    },
                },
            },
            "required": ["server_time", "domains"],
        },
        annotations=ToolAnnotations(readOnlyHint=True),
    ),
    Tool(
        name="get_record_schema",
        description=(
            "Return the required and optional content fields for one or all record types. "
            "The write_* tools already enforce their required fields — call this to check "
            "optional fields (e.g. date on decisions), or before edit_record to avoid "
            "field-name errors."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["convention", "pattern", "failure", "decision", "reference", "guide"],
                    "description": "Omit to return schemas for all types.",
                },
            },
        },
        annotations=ToolAnnotations(readOnlyHint=True),
    ),
    Tool(
        name="get_record_history",
        description=(
            "Show the write/edit/delete timeline for one record, including who "
            "changed what and the pre-edit value of each changed field. Use this "
            "before trusting a record's current content when it shows an edit "
            "count, or when a supersession warning points here for prior text."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "Record ID (mx-xxxxxx)"},
            },
            "required": ["record_id"],
        },
        annotations=ToolAnnotations(readOnlyHint=True),
    ),
    Tool(
        name="record_outcome",
        description=(
            "Record whether a record's guidance worked when applied. This directly "
            "improves search ranking — ml boosts confirmed records over unconfirmed "
            "ones. Call this proactively after applying a record's guidance and "
            "observing the result, the same way you'd call write_* for a new decision."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "Record ID (mx-xxxxxx)"},
                "domain": {
                    "type": "string",
                    "description": "The record's own domain (lookup key, not the context the outcome applies to)",
                },
                "status": {"type": "string", "enum": ["success", "failure", "partial"]},
                "notes": {
                    "type": "string",
                    "description": "Optional context, e.g. what was applied and where",
                },
            },
            "required": ["record_id", "domain", "status"],
        },
        annotations=ToolAnnotations(destructiveHint=False),
    ),
    Tool(
        name="edit_record",
        description=(
            "Update fields on an existing record. "
            "Writers may only edit their own records; admins may edit any record. "
            "Pass only the fields you want to change."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "Record ID (mx-xxxxxx)"},
                "domain": {"type": "string"},
                "classification": _CLASSIFICATION_PROPERTY,
                "title": {"type": "string", "description": "decision: title field"},
                "rationale": {"type": "string", "description": "decision: rationale field"},
                "content": {"type": "string", "description": "convention: body text"},
                "description": {
                    "type": "string",
                    "description": "failure/pattern/reference/guide: description field",
                },
                "resolution": {"type": "string", "description": "failure: resolution field"},
                "name": {"type": "string", "description": "pattern/reference/guide: name field"},
                **_RELATED_RECORD_PROPERTIES,
            },
            "required": ["record_id", "domain"],
        },
        annotations=ToolAnnotations(destructiveHint=True),
    ),
    Tool(
        name="delete_record",
        description=(
            "Delete a record by ID. "
            "Writers may only delete their own records; admins may delete any record. "
            "If this is the last record in the domain, the domain is removed automatically."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "Record ID (mx-xxxxxx)"},
                "domain": {"type": "string"},
            },
            "required": ["record_id", "domain"],
        },
        annotations=ToolAnnotations(destructiveHint=True),
    ),
    Tool(
        name="move_record",
        description=(
            "Move a record from one domain to another, preserving its ID — use this "
            "when a record landed in the wrong domain. "
            "Writers may only move their own records; admins may move any record. "
            "The target domain must already exist; this does not auto-create it "
            "like the write_* tools do. If this was the last record in the source "
            "domain, the domain is removed automatically."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "Record ID (mx-xxxxxx)"},
                "domain": {"type": "string", "description": "Current (source) domain"},
                "target_domain": {"type": "string", "description": "Destination domain"},
            },
            "required": ["record_id", "domain", "target_domain"],
        },
        annotations=ToolAnnotations(destructiveHint=True),
    ),
]

_RECORD_SCHEMAS: dict[str, dict] = {
    "convention": {"required": {"content": "string"}, "optional": {}},
    "decision": {
        "required": {"title": "string", "rationale": "string"},
        "optional": {"date": "string"},
    },
    "failure": {"required": {"description": "string", "resolution": "string"}, "optional": {}},
    "pattern": {
        "required": {"name": "string", "description": "string"},
        "optional": {"files": "array of strings"},
    },
    "reference": {
        "required": {"name": "string", "description": "string"},
        "optional": {"files": "array of strings"},
    },
    "guide": {"required": {"name": "string", "description": "string"}, "optional": {}},
}

# ml's own dedup key per type (mulch-cli 0.10.7 registry/builtins.ts). ml
# treats a new record matching an existing one of the same type on this field
# as a duplicate: convention/failure are "anonymous" (silently skipped, not
# written); decision/pattern/reference/guide are "named" (silently upserted
# in place, overwriting the existing record's other fields). Both outcomes
# omit the record object from ml's --stdin JSON response, which is what the
# duplicate pre-check in _record_expertise exists to avoid triggering.
_DEDUP_FIELD_BY_TYPE: dict[str, str] = {
    "convention": "content",
    "decision": "title",
    "failure": "description",
    "pattern": "name",
    "reference": "name",
    "guide": "name",
}
