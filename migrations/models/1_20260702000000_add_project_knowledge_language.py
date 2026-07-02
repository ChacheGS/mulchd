from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "projects" ADD COLUMN "knowledge_language" VARCHAR(16) NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "projects" DROP COLUMN "knowledge_language";"""


MODELS_STATE = (
    "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"
)
