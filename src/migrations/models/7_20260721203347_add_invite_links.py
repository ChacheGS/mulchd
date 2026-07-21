from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "invite_links" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "token" VARCHAR(64) NOT NULL UNIQUE,
    "role" VARCHAR(16) NOT NULL DEFAULT 'writer',
    "max_uses" INT,
    "use_count" INT NOT NULL DEFAULT 0,
    "expires_at" TIMESTAMPTZ,
    "allowed_email_domains" JSONB,
    "revoked" BOOL NOT NULL DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by_id" INT REFERENCES "users" ("id") ON DELETE CASCADE,
    "project_id" INT NOT NULL REFERENCES "projects" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "invite_links"."role" IS 'READER: reader\nWRITER: writer\nADMIN: admin';
        CREATE TABLE IF NOT EXISTS "invite_uses" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "used_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "invite_id" INT NOT NULL REFERENCES "invite_links" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "invite_uses";
        DROP TABLE IF EXISTS "invite_links";"""


MODELS_STATE = (
    "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"
    "4="
)
