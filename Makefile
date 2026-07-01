.PHONY: format test coverage dev dev-down dev-logs migrate-up migrate backup restore

COMPOSE     = docker compose -f deploy/docker-compose.yml
COMPOSE_DEV = $(COMPOSE) -f deploy/docker-compose.local.yml
BACKUP_DIR ?= backups

# ---------------------------------------------------------------------------
# Dev
# ---------------------------------------------------------------------------

dev:
	$(COMPOSE_DEV) up --build mulchd postgres

dev-down:
	$(COMPOSE_DEV) down

dev-logs:
	$(COMPOSE_DEV) logs -f mulchd postgres

# Generate a new aerich migration after model changes.
# Requires the dev postgres to be running (make migrate-up first).
migrate-up:
	$(COMPOSE_DEV) up -d postgres

migrate:
	MULCHD_SECRET_KEY=dev MULCHD_ADMIN_PASSWORD=dev \
	MULCHD_DB_URL="asyncpg://mulchd:devpassword@localhost:5433/mulchd" \
	uv run aerich migrate

format:
	uv run isort src/ tests/
	uv run black src/ tests/

typecheck:
	uv run pyright

test:
	uv run pytest tests/ -v

coverage:
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
