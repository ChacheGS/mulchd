from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "record_meta" DROP CONSTRAINT "record_meta_pkey";
        ALTER TABLE "record_meta" ADD COLUMN "id" SERIAL NOT NULL PRIMARY KEY;
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_record_meta_project_dfe5ac" ON "record_meta" ("project_id", "record_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_record_meta_project_dfe5ac";
        ALTER TABLE "record_meta" DROP CONSTRAINT "record_meta_pkey";
        ALTER TABLE "record_meta" DROP COLUMN "id";
        ALTER TABLE "record_meta" ADD PRIMARY KEY ("record_id");"""


MODELS_STATE = (
    "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"
    "Dz80zETHR+ieX8EiXiJqqfWL7/H7538Ik="
)
