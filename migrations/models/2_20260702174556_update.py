from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "tool_calls" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "tool" VARCHAR(64) NOT NULL,
    "client" VARCHAR(64) NOT NULL DEFAULT 'unknown',
    "called_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "author_id" INT REFERENCES "users" ("id") ON DELETE CASCADE,
    "project_id" INT NOT NULL REFERENCES "projects" ("id") ON DELETE CASCADE
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "tool_calls";"""


MODELS_STATE = (
    "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"
    "DtDTr/ZBE9/zDsZqm2rKCbx2V26VgW/wP8P6Kr"
)
