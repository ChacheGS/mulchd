#!/usr/bin/env python3
"""
Seed a mulchd instance with demo data.

Creates three users (alice/admin, bob/writer, claude/reader), one project,
~20 knowledge records across four domains, security-showcase audit events
(cross-owner edit, foundational supersession, classification downgrade,
cross-domain supersession), and ~100 tool-call entries spread over three weeks.

Usage:
    uv run scripts/seed.py

Idempotent: exits immediately if the 'alice' user already exists.
Requires the SQLite backend (default for local dev).
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running from repo root or from scripts/
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

os.environ.setdefault("MULCHD_SECRET_KEY", "seed-secret-key-not-for-production")
os.environ.setdefault("MULCHD_DB_URL", "sqlite://demo.db")
os.environ.setdefault("MULCHD_DATA_PATH", ".mulch-demo")

from tortoise import Tortoise, connections  # noqa: E402

from mulchd.admin_grants import grant_superadmin  # noqa: E402
from mulchd.auth import create_project_token, create_user  # noqa: E402
from mulchd.config import TORTOISE_ORM  # noqa: E402
from mulchd.domains import mulch_dir  # noqa: E402
from mulchd.models import (  # noqa: E402
    Organization,
    Project,
    RecordEdit,
    RecordEvent,
    RecordMeta,
    Role,
    ToolCall,
    User,
    UserMembership,
)
from mulchd.mulch import delete_record, edit_record, init_ml_project, write_record  # noqa: E402

ORG = "acme"
PROJECT = "backend-api"
NOW = datetime.now(timezone.utc)


def ago(**kwargs: int) -> datetime:
    return NOW - timedelta(**kwargs)


async def _backdate(table: str, pk: str | int, col: str, dt: datetime, pk_col: str = "id") -> None:
    """Set an auto_now_add timestamp after the fact via raw SQL."""
    conn = connections.get("default")
    dt_str = dt.strftime("%Y-%m-%d %H:%M:%S.%f+00:00")
    if isinstance(pk, str):
        await conn.execute_query(
            f"UPDATE {table} SET {col} = '{dt_str}' WHERE {pk_col} = '{pk}'"
        )
    else:
        await conn.execute_query(
            f"UPDATE {table} SET {col} = '{dt_str}' WHERE {pk_col} = {pk}"
        )


async def _write(
    m_dir: Path,
    domain: str,
    rec: dict,
    user: User,
    project: Project,
    dt: datetime,
    client: str = "claude-code",
) -> str:
    """Write a record and create the accompanying RecordMeta + RecordEvent."""
    result = await write_record(m_dir, domain, rec)
    record_id = result["id"]
    session_id = uuid.uuid4()

    await RecordMeta.create(
        record_id=record_id,
        project=project,
        domain=domain,
        author=user,
        session_id=session_id,
        client=client,
    )
    await _backdate("record_meta", record_id, "written_at", dt, pk_col="record_id")

    event = await RecordEvent.create(
        record_id=record_id,
        project=project,
        domain=domain,
        actor=user,
        action="write",
        client=client,
        session_id=session_id,
    )
    await _backdate("record_events", event.id, "at", dt)

    return record_id


async def main() -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()

    if await User.filter(username="alice").exists():
        print("Already seeded — nothing to do.")
        await Tortoise.close_connections()
        return

    print("Seeding demo data…")

    # ── Users ──────────────────────────────────────────────────────────────
    alice, alice_global = await create_user("alice", "Alice Chen")
    await grant_superadmin(alice, granted_by=alice)
    bob, bob_global = await create_user("bob", "Bob Ramos")
    claude, claude_global = await create_user("claude", "Claude")

    # ── Org + project ──────────────────────────────────────────────────────
    org = await Organization.create(slug=ORG, display_name="Acme Engineering")
    project = await Project.create(slug=PROJECT, display_name="Backend API", org=org)

    # ── Memberships: alice=admin, bob=writer, claude=reader ─────────────────
    await UserMembership.create(user=alice, project=project, role=Role.ADMIN)
    await UserMembership.create(user=bob, project=project, role=Role.WRITER)
    await UserMembership.create(user=claude, project=project, role=Role.READER)

    # ── Project tokens ──────────────────────────────────────────────────────
    _, alice_pt = await create_project_token(alice, project, label="alice-macbook")
    _, bob_pt = await create_project_token(bob, project, label="bob-workstation")
    _, claude_pt = await create_project_token(claude, project, label="claude-code")

    print(f"\n  Global tokens (for /connect):")
    print(f"    alice:  {alice_global}")
    print(f"    bob:    {bob_global}")
    print(f"    claude: {claude_global}")
    print(f"\n  Project tokens (for MCP .mcp.json):")
    print(f"    alice:  {alice_pt}")
    print(f"    bob:    {bob_pt}")
    print(f"    claude: {claude_pt}")

    # ── Init mulch project ──────────────────────────────────────────────────
    m_dir = mulch_dir(ORG, PROJECT)
    await init_ml_project(m_dir)

    # ── Knowledge records ───────────────────────────────────────────────────
    print("\n  Writing knowledge records…")

    # architecture — 7 records (including 1 to be deleted)
    auth_jwt_id = await _write(m_dir, "architecture", {
        "type": "decision",
        "classification": "foundational",
        "owner": "alice",
        "title": "JWT access tokens (1h) + refresh tokens (7d) for stateless auth",
        "rationale": (
            "Stateless tokens scale horizontally with no session store. Short access TTL limits "
            "blast radius on leak; refresh tokens allow revocation via a blocklist if needed. "
            "Chosen over server-side sessions to avoid a Redis dependency at launch."
        ),
        "date": ago(days=21).strftime("%Y-%m-%d"),
    }, alice, project, ago(days=21))

    await _write(m_dir, "architecture", {
        "type": "decision",
        "classification": "foundational",
        "owner": "alice",
        "title": "REST API with versioned routes under /api/v{n}",
        "rationale": (
            "REST is well-understood by consumers and tooling. Versioning in the path (not headers) "
            "keeps routes inspectable and cache-friendly. GraphQL was evaluated and rejected — query "
            "complexity overhead outweighed flexibility for our read patterns."
        ),
        "date": ago(days=21).strftime("%Y-%m-%d"),
    }, alice, project, ago(days=21, hours=1))

    await _write(m_dir, "architecture", {
        "type": "pattern",
        "classification": "tactical",
        "owner": "alice",
        "name": "Repository pattern for data access",
        "description": (
            "One repository class per model, all methods async. Callers never import the ORM "
            "directly — they go through the repository. Keeps query logic in one place and "
            "makes testing straightforward without mocking the ORM."
        ),
    }, alice, project, ago(days=20))

    await _write(m_dir, "architecture", {
        "type": "decision",
        "classification": "tactical",
        "owner": "bob",
        "title": "async SQLAlchemy 2.0 with Alembic for DB access and migrations",
        "rationale": (
            "SQLAlchemy 2.0 native async avoids the greenlet shim. Alembic handles schema "
            "migrations with autogenerate support. Chosen over raw asyncpg for ORM ergonomics "
            "and existing team familiarity."
        ),
        "date": ago(days=19).strftime("%Y-%m-%d"),
    }, bob, project, ago(days=19))

    # Supersedes alice's JWT decision — cross-owner foundational supersession
    await _write(m_dir, "architecture", {
        "type": "decision",
        "classification": "foundational",
        "owner": "bob",
        "title": "Replace JWT with server-side sessions backed by Redis",
        "rationale": (
            "JWT refresh token revocation requires a blocklist, which is effectively a session "
            "store anyway. Redis sessions are simpler to reason about and support instant "
            "revocation. Ops overhead is acceptable now that Redis is in the stack for queues."
        ),
        "date": ago(days=14).strftime("%Y-%m-%d"),
        "supersedes": [auth_jwt_id],
    }, bob, project, ago(days=14))

    # Cross-domain supersession + classification downgrade:
    # tactical pattern in architecture supersedes foundational convention in conventions.
    # The conventions record ID is written below; we patch supersedes after the fact
    # by writing the architecture record last (see below).

    # Archived record: alice explores GraphQL, rejects it, later deletes the record
    graphql_id = await _write(m_dir, "architecture", {
        "type": "decision",
        "classification": "tactical",
        "owner": "alice",
        "title": "Spike: evaluate GraphQL for the public API surface",
        "rationale": (
            "Exploring whether GraphQL would reduce client-side over-fetching. Ultimately "
            "rejected — query complexity overhead and tooling immaturity outweigh the "
            "flexibility gains for our access patterns. Closing this out."
        ),
        "date": ago(days=20).strftime("%Y-%m-%d"),
    }, alice, project, ago(days=20, hours=4))

    # conventions — 5 records
    versioning_id = await _write(m_dir, "conventions", {
        "type": "convention",
        "classification": "foundational",
        "owner": "alice",
        # Intentionally slightly wrong — bob will edit this (cross-owner edit showcase)
        "content": "All API routes prefixed /api with no versioning plan.",
    }, alice, project, ago(days=21, hours=2))

    pagination_conv_id = await _write(m_dir, "conventions", {
        "type": "convention",
        "classification": "foundational",
        "owner": "alice",
        "content": (
            "Paginate collections with ?page=N&per_page=M (default 20, max 100). "
            "Return meta.total_count and links.next in the envelope."
        ),
    }, alice, project, ago(days=21, hours=3))

    await _write(m_dir, "conventions", {
        "type": "convention",
        "classification": "tactical",
        "owner": "alice",
        "content": (
            "Error responses follow RFC 7807 Problem Details: JSON body with type (URI), "
            "title, status, and detail. Validation errors include an errors array with "
            "per-field messages."
        ),
    }, alice, project, ago(days=20, hours=1))

    await _write(m_dir, "conventions", {
        "type": "guide",
        "classification": "tactical",
        "owner": "bob",
        "name": "Local development setup",
        "description": (
            "docker compose up starts Postgres and Redis. Run the API natively: "
            "uv run uvicorn app.main:app --reload. Run alembic upgrade head before "
            "the first start. Copy .env.example to .env and fill in SECRET_KEY."
        ),
    }, bob, project, ago(days=19, hours=2))

    await _write(m_dir, "conventions", {
        "type": "convention",
        "classification": "tactical",
        "owner": "claude",
        "content": (
            "Log structured JSON to stdout. Default level INFO in production. "
            "Override with LOG_LEVEL env var. Never log request bodies or "
            "Authorization headers — scrub at the middleware layer."
        ),
    }, claude, project, ago(days=10))

    # Now write the cross-domain supersession record (tactical arch supersedes
    # foundational conventions/pagination — classification downgrade badge).
    await _write(m_dir, "architecture", {
        "type": "pattern",
        "classification": "tactical",
        "owner": "claude",
        "name": "Cursor-based pagination for collection endpoints",
        "description": (
            "Encode (created_at, id) as a base64 opaque cursor. Avoids skip/duplicate "
            "edge cases of page+offset when rows are inserted between pages. Response "
            "includes next_cursor: null on the last page. Supersedes page-based convention."
        ),
        "supersedes": [pagination_conv_id],
    }, claude, project, ago(days=7))

    # ops — 4 records
    await _write(m_dir, "ops", {
        "type": "decision",
        "classification": "foundational",
        "owner": "alice",
        "title": "Deploy to Railway with managed Postgres and Redis",
        "rationale": (
            "Railway handles TLS, managed databases, and cron jobs with minimal ops overhead. "
            "Cost is acceptable at current scale. Evaluated Fly.io and Render; Railway won "
            "on ease of Redis provisioning and the deploy-from-git workflow."
        ),
        "date": ago(days=20, hours=2).strftime("%Y-%m-%d"),
    }, alice, project, ago(days=20, hours=2))

    await _write(m_dir, "ops", {
        "type": "guide",
        "classification": "tactical",
        "owner": "bob",
        "name": "Database backup procedure",
        "description": (
            "Railway runs pg_dump daily via its cron integration. Dumps land in S3 "
            "(bucket: acme-backups, prefix: backend-api/db/). Retention: 30 days. "
            "To restore: download the dump, spin up local Postgres, pg_restore, verify, promote."
        ),
    }, bob, project, ago(days=17))

    await _write(m_dir, "ops", {
        "type": "guide",
        "classification": "tactical",
        "owner": "alice",
        "name": "Adding a new environment variable",
        "description": (
            "1) Add to .env.example with a placeholder and a comment. "
            "2) Add to the Settings Pydantic model in config.py. "
            "3) Add to Railway for each environment. "
            "4) If it's a secret, add to GitHub Actions secrets. Never commit actual values."
        ),
    }, alice, project, ago(days=15))

    await _write(m_dir, "ops", {
        "type": "failure",
        "classification": "tactical",
        "owner": "claude",
        "description": (
            "The /health endpoint was behind auth middleware. Railway health checks "
            "carry no auth header, so the container cycled with 401s for 20 minutes "
            "before we noticed."
        ),
        "resolution": (
            "Moved /health to a router mounted at app level before AuthMiddleware. "
            "Added an integration test that hits /health without a token."
        ),
    }, claude, project, ago(days=12))

    # testing — 4 records
    await _write(m_dir, "testing", {
        "type": "decision",
        "classification": "foundational",
        "owner": "alice",
        "title": "pytest + pytest-asyncio with factory_boy; real test DB, no mocks",
        "rationale": (
            "Mocking the DB caught none of the three regressions in month one — they were "
            "all query or migration issues that only surface against a real DB. factory_boy "
            "gives clean fixture factories. asyncio_mode=auto in pytest.ini removes boilerplate."
        ),
        "date": ago(days=18).strftime("%Y-%m-%d"),
    }, alice, project, ago(days=18))

    await _write(m_dir, "testing", {
        "type": "convention",
        "classification": "tactical",
        "owner": "bob",
        "content": (
            "tests/unit/ for pure-function tests with no DB or network. "
            "tests/integration/ for anything that touches the DB, HTTP client, or "
            "external services. Integration tests run separately in CI: pytest -m integration."
        ),
    }, bob, project, ago(days=17, hours=1))

    await _write(m_dir, "testing", {
        "type": "pattern",
        "classification": "tactical",
        "owner": "claude",
        "name": "Parametrize boundary conditions",
        "description": (
            "Always cover: empty collection, single item, exactly at the limit "
            "(e.g. per_page=100), and one over the limit. "
            "One test function with pytest.mark.parametrize — four cases, zero repetition."
        ),
    }, claude, project, ago(days=10, hours=2))

    await _write(m_dir, "testing", {
        "type": "failure",
        "classification": "tactical",
        "owner": "bob",
        "description": (
            "Async fixtures with default scope='function' deadlock when the event loop "
            "is reused across tests. Spent two hours on mysterious hangs before finding this."
        ),
        "resolution": (
            "Set asyncio_mode = auto in pytest.ini. Use @pytest_asyncio.fixture and set "
            "scope='session' for the DB fixture. See pytest-asyncio docs on loop scope."
        ),
    }, bob, project, ago(days=9))

    # ── Security showcase events ─────────────────────────────────────────────
    print("  Creating security-showcase events…")

    # 1. Cross-owner edit: bob corrects alice's versioning convention
    edit_dt = ago(days=13)
    edit_session = uuid.uuid4()
    await edit_record(m_dir, "conventions", versioning_id, {
        "content": "All API routes prefixed /api; bump the version prefix to /api/v2 only on breaking changes.",
    })
    edit_ev = await RecordEvent.create(
        record_id=versioning_id,
        project=project,
        domain="conventions",
        actor=bob,
        action="edit",
        client="cursor",
        session_id=edit_session,
    )
    await _backdate("record_events", edit_ev.id, "at", edit_dt)
    edit_rec = await RecordEdit.create(
        record_id=versioning_id,
        project=project,
        domain="conventions",
        actor=bob,
        before_snapshot={"content": "All API routes prefixed /api with no versioning plan."},
        client="cursor",
        session_id=edit_session,
    )
    await _backdate("record_edits", edit_rec.id, "at", edit_dt)

    # 2. Soft-delete: alice archives the GraphQL spike record
    delete_dt = ago(days=18, hours=2)
    await delete_record(m_dir, "architecture", graphql_id)
    del_session = uuid.uuid4()
    del_ev = await RecordEvent.create(
        record_id=graphql_id,
        project=project,
        domain="architecture",
        actor=alice,
        action="delete",
        client="claude-code",
        session_id=del_session,
    )
    await _backdate("record_events", del_ev.id, "at", delete_dt)

    # ── Tool-call history (~100 calls over 3 weeks) ──────────────────────────
    print("  Generating tool-call history…")

    roster = [
        (alice, "claude-code"),
        (alice, "cursor"),
        (bob, "claude-code"),
        (bob, "cursor"),
        (claude, "claude-code"),
        (claude, "claude-desktop"),
    ]
    # Repeat each tool proportionally to its expected call frequency
    tool_pool = (
        ["list_domains"] * 14
        + ["read_records"] * 24
        + ["write_record"] * 20
        + ["search_records"] * 22
        + ["get_recent"] * 12
        + ["edit_record"] * 4
        + ["get_record_schema"] * 4
    )  # 100 entries

    # Spread across three weeks: density increases toward the present
    day_plan = (
        [(ago(days=d), 3) for d in range(21, 14, -1)]  # week 1: ~3/day
        + [(ago(days=d), 5) for d in range(14, 7, -1)]  # week 2: ~5/day
        + [(ago(days=d), 7) for d in range(7, 1, -1)]   # week 3: ~7/day
    )

    call_idx = 0
    for base_dt, count in day_plan:
        for i in range(count):
            user, client = roster[call_idx % len(roster)]
            tool = tool_pool[call_idx % len(tool_pool)]
            dt = base_dt + timedelta(hours=i * 2, minutes=(call_idx * 7) % 53)
            tc = await ToolCall.create(project=project, author=user, tool=tool, client=client)
            await _backdate("tool_calls", tc.id, "called_at", dt)
            call_idx += 1

    total_calls = await ToolCall.filter(project=project).count()
    total_events = await RecordEvent.filter(project=project).count()

    print(f"\n  {total_calls} tool calls, {total_events} audit events.")
    await Tortoise.close_connections()
    print("\nDone. Start the server and open /admin to explore.")


if __name__ == "__main__":
    asyncio.run(main())
