from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "admin_grants" DROP CONSTRAINT IF EXISTS "admin_grants_user_id_fkey";
        ALTER TABLE "admin_grants" ADD CONSTRAINT "admin_grants_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users" ("id") ON DELETE RESTRICT;
        ALTER TABLE "admin_grants" DROP CONSTRAINT IF EXISTS "admin_grants_granted_by_id_fkey";
        ALTER TABLE "admin_grants" ADD CONSTRAINT "admin_grants_granted_by_id_fkey" FOREIGN KEY ("granted_by_id") REFERENCES "users" ("id") ON DELETE RESTRICT;
        ALTER TABLE "admin_grants" DROP CONSTRAINT IF EXISTS "admin_grants_revoked_by_id_fkey";
        ALTER TABLE "admin_grants" ADD CONSTRAINT "admin_grants_revoked_by_id_fkey" FOREIGN KEY ("revoked_by_id") REFERENCES "users" ("id") ON DELETE RESTRICT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "admin_grants" DROP CONSTRAINT IF EXISTS "admin_grants_revoked_by_id_fkey";
        ALTER TABLE "admin_grants" ADD CONSTRAINT "admin_grants_revoked_by_id_fkey" FOREIGN KEY ("revoked_by_id") REFERENCES "users" ("id") ON DELETE CASCADE;
        ALTER TABLE "admin_grants" DROP CONSTRAINT IF EXISTS "admin_grants_granted_by_id_fkey";
        ALTER TABLE "admin_grants" ADD CONSTRAINT "admin_grants_granted_by_id_fkey" FOREIGN KEY ("granted_by_id") REFERENCES "users" ("id") ON DELETE CASCADE;
        ALTER TABLE "admin_grants" DROP CONSTRAINT IF EXISTS "admin_grants_user_id_fkey";
        ALTER TABLE "admin_grants" ADD CONSTRAINT "admin_grants_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users" ("id") ON DELETE CASCADE;"""


MODELS_STATE = (
    "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"
    "GVlfnMY6YQLpq/Ppqyvs+da/sDz/C8l0uDs="
)
