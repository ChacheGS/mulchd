import os

import pytest
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

os.environ.setdefault("MULCHD_SECRET_KEY", "test-secret-key")
os.environ.setdefault("MULCHD_ADMIN_PASSWORD", "testpass")
os.environ.setdefault("MULCHD_DB_URL", "sqlite://:memory:")

from mulchd.main import app  # noqa: E402 — env must be set before import


@pytest.fixture(autouse=True)
async def db():
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["mulchd.models", "aerich.models"]},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.fixture
async def client(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def admin_client(client):
    """AsyncClient with an active admin session cookie."""
    resp = await client.post("/admin/login", data={"password": "testpass"})
    assert resp.status_code in (200, 303)
    return client
