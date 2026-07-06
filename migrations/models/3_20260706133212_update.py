from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "record_events" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "record_id" VARCHAR(32) NOT NULL,
    "domain" VARCHAR(64) NOT NULL,
    "action" VARCHAR(16) NOT NULL,
    "client" VARCHAR(64) NOT NULL DEFAULT 'unknown',
    "session_id" UUID,
    "at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "actor_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    "project_id" INT NOT NULL REFERENCES "projects" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "record_events" IS 'Out-of-band audit log for every mutating action on a record.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "record_events";"""


MODELS_STATE = (
    "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"
)
