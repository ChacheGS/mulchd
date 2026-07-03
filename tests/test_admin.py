import pytest


async def test_login_page_renders(client):
    resp = await client.get("/admin/login")
    assert resp.status_code == 200
    assert "mulchd" in resp.text


async def test_login_wrong_password(client):
    resp = await client.post("/admin/login", data={"password": "wrong"}, follow_redirects=False)
    assert resp.status_code == 401
    assert "Incorrect password" in resp.text


async def test_login_correct_password_redirects(client):
    resp = await client.post("/admin/login", data={"password": "testpass"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/"


async def test_dashboard_requires_auth(client):
    resp = await client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/admin/login" in resp.headers["location"]


async def test_dashboard_renders(admin_client):
    resp = await admin_client.get("/admin/")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


async def test_create_user(admin_client):
    resp = await admin_client.post(
        "/admin/users",
        data={"username": "jorge", "display_name": "Jorge M."},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/users/created"


async def test_create_user_duplicate(admin_client):
    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge"})
    resp = await admin_client.post(
        "/admin/users",
        data={"username": "jorge", "display_name": "Jorge 2"},
        follow_redirects=False,
    )
    assert resp.status_code == 409
    assert "already taken" in resp.text


async def test_token_reveal_page(admin_client):
    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge M."})
    resp = await admin_client.get("/admin/users/created")
    assert resp.status_code == 200
    assert "jorge" in resp.text
    assert "/onboard" in resp.text  # setup guide URL shown on token reveal page


async def test_token_reveal_clears_on_revisit(admin_client):
    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge M."})
    await admin_client.get("/admin/users/created")
    resp = await admin_client.get("/admin/users/created", follow_redirects=False)
    assert resp.status_code == 303


async def test_create_org(admin_client):
    resp = await admin_client.post(
        "/admin/orgs", data={"slug": "acme", "display_name": "Acme Corp"}, follow_redirects=False
    )
    assert resp.status_code == 303


async def test_create_project(admin_client):
    await admin_client.post("/admin/orgs", data={"slug": "acme", "display_name": "Acme"})
    resp = await admin_client.get("/admin/orgs")
    from mulchd.models import Organization

    org = await Organization.get(slug="acme")
    resp = await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "data-platform", "display_name": "Data Platform"},
        follow_redirects=False,
    )
    assert resp.status_code == 303


async def test_add_membership(admin_client):
    await admin_client.post("/admin/orgs", data={"slug": "acme", "display_name": "Acme"})
    from mulchd.models import Organization

    org = await Organization.get(slug="acme")
    await admin_client.post(
        "/admin/projects",
        data={"org_id": org.id, "slug": "proj", "display_name": "Proj"},
    )
    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge M."})

    from mulchd.models import Project, User

    user = await User.get(username="jorge")
    project = await Project.get(slug="proj")

    resp = await admin_client.post(
        "/admin/memberships",
        data={"user_id": user.id, "project_id": project.id, "role": "writer"},
        follow_redirects=False,
    )
    assert resp.status_code == 303


async def test_deactivate_user(admin_client):
    await admin_client.post("/admin/users", data={"username": "jorge", "display_name": "Jorge M."})
    from mulchd.models import User

    user = await User.get(username="jorge")
    resp = await admin_client.post(f"/admin/users/{user.id}/deactivate", follow_redirects=False)
    assert resp.status_code == 303
    await user.refresh_from_db()
    assert not user.active


async def test_users_page_renders(admin_client):
    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    assert "Add user" in resp.text


async def test_records_count_requires_auth(client, tmp_path, monkeypatch):
    from mulchd.config import settings
    monkeypatch.setattr(settings, "data_path", tmp_path)
    resp = await client.get("/admin/records/count?project=acme/demo", follow_redirects=False)
    assert resp.status_code == 303
    assert "/admin/login" in resp.headers["location"]


async def test_records_count_no_project(admin_client, tmp_path, monkeypatch):
    from mulchd.config import settings
    monkeypatch.setattr(settings, "data_path", tmp_path)
    resp = await admin_client.get("/admin/records/count")
    assert resp.status_code == 200
    assert resp.json() == {"count": 0}


async def test_records_count_with_jsonl(admin_client, tmp_path, monkeypatch):
    from mulchd.config import settings
    monkeypatch.setattr(settings, "data_path", tmp_path)
    expertise = tmp_path / "acme" / "demo" / ".mulch" / "expertise"
    expertise.mkdir(parents=True)
    (expertise / "architecture.jsonl").write_text(
        '{"id":"mx-aaa","type":"decision"}\n{"id":"mx-bbb","type":"convention"}\n'
    )
    (expertise / "ops.jsonl").write_text(
        '{"id":"mx-ccc","type":"guide"}\n'
    )
    resp = await admin_client.get("/admin/records/count?project=acme/demo")
    assert resp.status_code == 200
    assert resp.json() == {"count": 3}
