from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "oauth_clients" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "client_id" VARCHAR(64) NOT NULL UNIQUE,
    "client_metadata" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE "oauth_clients" IS 'A dynamically-registered MCP client (RFC 7591).';
        CREATE TABLE IF NOT EXISTS "oauth_grants" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "client_id" INT NOT NULL REFERENCES "oauth_clients" ("id") ON DELETE CASCADE,
    "project_id" INT NOT NULL REFERENCES "projects" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_oauth_grant_client__a7379a" UNIQUE ("client_id", "user_id")
);
COMMENT ON TABLE "oauth_grants" IS 'A remembered user consent for one client, scoped to one project.';
        CREATE TABLE IF NOT EXISTS "oauth_codes" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "code_hash" VARCHAR(64) NOT NULL UNIQUE,
    "client_id" VARCHAR(64) NOT NULL,
    "redirect_uri" VARCHAR(512) NOT NULL,
    "code_challenge" VARCHAR(128) NOT NULL,
    "scope" VARCHAR(255),
    "expires_at" TIMESTAMPTZ NOT NULL,
    "used" BOOL NOT NULL DEFAULT False,
    "grant_id" INT NOT NULL REFERENCES "oauth_grants" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "oauth_codes" IS 'A short-lived, single-use authorization code.';
        CREATE TABLE IF NOT EXISTS "oauth_tokens" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "access_token_hash" VARCHAR(64) NOT NULL UNIQUE,
    "refresh_token_hash" VARCHAR(64) NOT NULL UNIQUE,
    "client_id" VARCHAR(64) NOT NULL,
    "scope" VARCHAR(255),
    "access_expires_at" TIMESTAMPTZ NOT NULL,
    "refresh_expires_at" TIMESTAMPTZ NOT NULL,
    "revoked" BOOL NOT NULL DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "grant_id" INT NOT NULL REFERENCES "oauth_grants" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "oauth_tokens" IS 'An issued access/refresh token pair.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "oauth_grants";
        DROP TABLE IF EXISTS "oauth_tokens";
        DROP TABLE IF EXISTS "oauth_codes";
        DROP TABLE IF EXISTS "oauth_clients";"""


MODELS_STATE = (
    "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"
    "lukKtxvln+0fM4Ez/bNn+leIm2h+Yvn1f72GFv0="
)
