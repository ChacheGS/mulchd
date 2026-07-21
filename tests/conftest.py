import os

import pytest
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

os.environ.setdefault("MULCHD_SECRET_KEY", "test-secret-key")
os.environ.setdefault("MULCHD_DB_URL", "sqlite://:memory:")

from mulchd.main import app  # noqa: E402 — env must be set before import


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "no_db: mark test as not requiring database fixture")


def pytest_collection_modifyitems(config, items):
    """Skip the db fixture for tests marked with no_db only in test_mcp_tiers.py."""
    for item in items:
        if "no_db" in item.keywords and "test_mcp_tiers.py" in str(item.fspath):
            item.fixturenames = [f for f in item.fixturenames if f != "db"]


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
    """AsyncClient authenticated as a real User holding an active SUPERADMIN grant."""
    from mulchd.admin_grants import grant_superadmin
    from mulchd.auth import create_user
    from mulchd.connect import _signer

    user, _ = await create_user("admin", "Admin")
    await grant_superadmin(user, granted_by=user)
    signed = _signer().dumps(user.id)
    client.cookies.set("mulchd_connect", signed)
    return client
