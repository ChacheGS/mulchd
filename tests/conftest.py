import os
import shutil
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

# node_modules/.bin/ml (the mulch CLI) isn't on PATH by default — add it if present.
if shutil.which("ml") is None:
    _bin_dir = Path(__file__).resolve().parent.parent / "node_modules" / ".bin"
    if (_bin_dir / "ml").exists():
        os.environ["PATH"] = f"{_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"

os.environ.setdefault("MULCHD_SECRET_KEY", "test-secret-key")
os.environ.setdefault("MULCHD_DB_URL", "sqlite://:memory:")
# MULCHD_HOST defaults to 0.0.0.0, which the mcp SDK's issuer-URL validation rejects
# (RFC 8414 requires HTTPS, with an explicit localhost/127.0.0.1 carve-out for testing).
# Point resolved_base_url at that carve-out so the OAuth routes can be registered.
os.environ.setdefault("MULCHD_HOST", "127.0.0.1")

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
    from mulchd.policies import _clear_policy_cache

    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["mulchd.models", "aerich.models"]},
    )
    await Tortoise.generate_schemas()
    # Each test gets a fresh in-memory DB with autoincrement IDs starting back
    # at 1, but policies.py's DB-override TTL cache is a module-global dict
    # keyed by (project.id, key) that outlives any single test. Without this,
    # a test that writes a ProjectPolicy override can poison the cache entry
    # for a later, unrelated test whose project happens to reuse the same id.
    _clear_policy_cache()
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
