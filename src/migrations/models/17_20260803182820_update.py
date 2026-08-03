from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "admin_grants" DROP CONSTRAINT IF EXISTS "fk_admin_gr_users_617cce45";
        ALTER TABLE "admin_grants" DROP COLUMN "revoked_at";
        ALTER TABLE "admin_grants" DROP COLUMN "revoked_by_id";
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_admin_grant_user_id_2e342b" ON "admin_grants" ("user_id", "role");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_admin_grant_user_id_2e342b";
        ALTER TABLE "admin_grants" ADD "revoked_at" TIMESTAMPTZ;
        ALTER TABLE "admin_grants" ADD "revoked_by_id" INT;
        ALTER TABLE "admin_grants" ADD CONSTRAINT "fk_admin_gr_users_617cce45" FOREIGN KEY ("revoked_by_id") REFERENCES "users" ("id") ON DELETE RESTRICT;"""


MODELS_STATE = (
    "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"
    "zX9Yvv8fvwcejA=="
)
