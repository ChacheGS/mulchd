#!/usr/bin/env bash
# Start a local mulchd demo server backed by a SQLite database.
# Seeds the database on first run; subsequent runs skip seeding.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEMO_DIR="$REPO_ROOT/demo"

mkdir -p "$DEMO_DIR"

cd "$DEMO_DIR"


export MULCHD_SECRET_KEY="${MULCHD_SECRET_KEY:-seed-secret-key-not-for-production}"
export MULCHD_ADMIN_PASSWORD="${MULCHD_ADMIN_PASSWORD:-admin}"
export MULCHD_DB_URL="${MULCHD_DB_URL:-sqlite://demo.db}"
export MULCHD_DATA_PATH="${MULCHD_DATA_PATH:-.mulch-demo}"
export MULCHD_PORT="${MULCHD_PORT:-8000}"
export MULCHD_HOST="${MULCHD_HOST:-127.0.0.1}"

uv run "$REPO_ROOT/scripts/seed.py"
uv run mulchd
