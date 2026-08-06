from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "project_policies" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "key" VARCHAR(64) NOT NULL,
    "value" JSONB NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "project_id" INT NOT NULL REFERENCES "projects" ("id") ON DELETE CASCADE,
    "updated_by_id" INT REFERENCES "users" ("id") ON DELETE SET NULL,
    CONSTRAINT "uid_project_pol_project_0a8a98" UNIQUE ("project_id", "key")
);
COMMENT ON TABLE "project_policies" IS 'A runtime override for one named policy, scoped to one project.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "project_policies";"""


MODELS_STATE = (
    "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"
    "z4P4MKz3U="
)
