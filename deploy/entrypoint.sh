#!/bin/sh
set -e

# Apply any pending migrations. On first boot with an empty migrations/
# directory this is a no-op; Tortoise's generate_schemas() in the app
# lifespan handles initial schema creation. Once aerich init-db has been
# run and migrations are committed, this picks them up on each deploy.
if find migrations -name '*.py' 2>/dev/null | grep -q .; then
    echo "Applying database migrations..."
    uv run aerich upgrade
fi

exec uv run mulchd
