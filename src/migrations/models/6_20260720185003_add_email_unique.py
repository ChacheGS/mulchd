from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_users_email_133a6f" ON "users" ("email");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "users" DROP CONSTRAINT IF EXISTS "users_email_key";
        DROP INDEX IF EXISTS "uid_users_email_133a6f";"""


MODELS_STATE = (
    "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"
)
