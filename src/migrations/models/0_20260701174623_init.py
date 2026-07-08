from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "organizations" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "slug" VARCHAR(64) NOT NULL UNIQUE,
    "display_name" VARCHAR(128) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "projects" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "slug" VARCHAR(64) NOT NULL,
    "display_name" VARCHAR(128) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "org_id" INT NOT NULL REFERENCES "organizations" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_projects_org_id_acb95b" UNIQUE ("org_id", "slug")
);
CREATE TABLE IF NOT EXISTS "users" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "username" VARCHAR(64) NOT NULL UNIQUE,
    "display_name" VARCHAR(128) NOT NULL,
    "token_hash" VARCHAR(64) NOT NULL,
    "active" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "project_tokens" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "token_hash" VARCHAR(64) NOT NULL UNIQUE,
    "label" VARCHAR(128) NOT NULL DEFAULT '',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "active" BOOL NOT NULL DEFAULT True,
    "project_id" INT NOT NULL REFERENCES "projects" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "record_meta" (
    "record_id" VARCHAR(32) NOT NULL PRIMARY KEY,
    "domain" VARCHAR(64) NOT NULL,
    "session_id" UUID NOT NULL,
    "client" VARCHAR(64) NOT NULL DEFAULT 'unknown',
    "written_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "author_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    "project_id" INT NOT NULL REFERENCES "projects" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "user_memberships" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "role" VARCHAR(16) NOT NULL DEFAULT 'writer',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "project_id" INT NOT NULL REFERENCES "projects" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_user_member_user_id_ae3f30" UNIQUE ("user_id", "project_id")
);
COMMENT ON COLUMN "user_memberships"."role" IS 'READER: reader\nWRITER: writer\nADMIN: admin';
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "lcZp+BZfkfLj618A=="
)
