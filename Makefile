.PHONY: format test coverage dev dev-inspector dev-down dev-logs migrate-up migrate backup restore bootstrap-admin

COMPOSE     = docker compose -f deploy/docker-compose.yml
COMPOSE_DEV = $(COMPOSE) -f deploy/docker-compose.local.yml
BACKUP_DIR ?= backups
DEV_DB_ENV  = MULCHD_SECRET_KEY=dev MULCHD_DB_URL="asyncpg://mulchd:devpassword@localhost:5433/mulchd"

# ---------------------------------------------------------------------------
# Dev
# ---------------------------------------------------------------------------

dev:
	$(COMPOSE_DEV) up --build mulchd 

dev-inspector:
	$(COMPOSE_DEV) --profile tools up inspector

dev-down:
	$(COMPOSE_DEV) down

dev-logs:
	$(COMPOSE_DEV) logs -f mulchd postgres

# Starts the dev postgres and applies any pending aerich migrations, so the
# schema is never stale after a `git pull` that added new migration files.
migrate-up:
	$(COMPOSE_DEV) up -d --wait postgres
	$(DEV_DB_ENV) uv run aerich upgrade

# Generate a new aerich migration after model changes.
# Requires the dev postgres to be running and current (make migrate-up first).
migrate:
	$(DEV_DB_ENV) uv run aerich migrate

format:
	uv run isort src/ tests/
	uv run black src/ tests/

# ml (the mulch CLI) some tests need; conftest.py puts it on PATH once installed.
node_modules/.bin/ml:
	bun install

typecheck:
	uv run pyright

test: node_modules/.bin/ml
	uv run pytest tests/ -v

coverage: node_modules/.bin/ml
	uv run pytest tests/ --cov --cov-report=term-missing

# ---------------------------------------------------------------------------
# Backup / restore
#
# backup: dumps postgres + all mulch JSONL stores into a single timestamped
#         tgz on the host.  Safe to run against the live service.
#
# restore FILE=backups/mulchd-backup-TIMESTAMP.tgz
#         Drops and recreates the postgres schema, then restores data.
#         The mulchd service is stopped first to avoid concurrent writes.
# ---------------------------------------------------------------------------

backup:
	@ts=$$(date +%Y%m%d_%H%M%S); \
	tmp=$$(mktemp -d); \
	echo "==> Dumping postgres..."; \
	$(COMPOSE) exec -T postgres \
	  pg_dump -U mulchd -Fc mulchd > "$$tmp/postgres.dump"; \
	echo "==> Archiving mulch expertise stores..."; \
	$(COMPOSE) exec -T mulchd \
	  tar -C /data -czf - mulch > "$$tmp/mulch.tar.gz"; \
	mkdir -p $(BACKUP_DIR); \
	tar -czf "$(BACKUP_DIR)/mulchd-backup-$$ts.tgz" -C "$$tmp" .; \
	rm -rf "$$tmp"; \
	echo "==> Backup saved: $(BACKUP_DIR)/mulchd-backup-$$ts.tgz"

restore:
	@if [ -z "$(FILE)" ]; then \
	  echo "Usage: make restore FILE=backups/mulchd-backup-TIMESTAMP.tgz"; \
	  exit 1; \
	fi
	@echo "==> Stopping mulchd..."; \
	$(COMPOSE) stop mulchd
	@tmp=$$(mktemp -d); \
	tar -xzf "$(FILE)" -C "$$tmp"; \
	echo "==> Restoring postgres..."; \
	$(COMPOSE) exec -T postgres \
	  pg_restore -U mulchd --clean --if-exists -d mulchd < "$$tmp/postgres.dump"; \
	echo "==> Restoring mulch expertise stores..."; \
	$(COMPOSE) exec -T mulchd \
	  tar -C /data -xzf - < "$$tmp/mulch.tar.gz"; \
	rm -rf "$$tmp"; \
	$(COMPOSE) start mulchd; \
	echo "==> Restore complete."

# Bootstrap the first admin against the live deployed container. Refuses if
# an admin already exists — see src/mulchd/cli.py.
# Usage: make bootstrap-admin USERNAME=carlos DISPLAY_NAME="Carlos G" EMAIL=carlos@example.com
bootstrap-admin:
	@if [ -z "$(USERNAME)" ] || [ -z "$(DISPLAY_NAME)" ] || [ -z "$(EMAIL)" ]; then \
	  echo "Usage: make bootstrap-admin USERNAME=<username> DISPLAY_NAME=\"<display name>\" EMAIL=<email>"; \
	  exit 1; \
	fi
	$(COMPOSE) exec mulchd .venv/bin/mulchd-bootstrap-admin \
	  --username "$(USERNAME)" --display-name "$(DISPLAY_NAME)" --email "$(EMAIL)"
