#!/bin/sh
set -e

# Build the database URL from the postgres env vars so the formula stays
# in version-controlled code rather than in a host-managed env file.
# POSTGRES_* arrive from env_file: postgres.env (see docker-compose.yml).
export MULCHD_DB_URL="asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"

# Apply any pending migrations. On first boot with an empty migrations/
# directory this is a no-op; Tortoise's generate_schemas() in the app
# lifespan handles initial schema creation. Once aerich init-db has been
# run and migrations are committed, this picks them up on each deploy.
if find migrations -name '*.py' 2>/dev/null | grep -q .; then
    echo "Applying database migrations..."
    .venv/bin/aerich upgrade
fi

exec .venv/bin/mulchd
