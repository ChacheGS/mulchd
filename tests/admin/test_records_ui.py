import pytest


async def test_records_count_requires_auth(client, tmp_path, monkeypatch):
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    resp = await client.get("/admin/records/count?project=acme/demo", follow_redirects=False)
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


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
    (expertise / "ops.jsonl").write_text('{"id":"mx-ccc","type":"guide"}\n')
    resp = await admin_client.get("/admin/records/count?project=acme/demo")
    assert resp.status_code == 200
    assert resp.json() == {"count": 3}


async def test_records_page_404s_for_unknown_project(admin_client):
    resp = await admin_client.get("/admin/p/nope/nope/records")
    assert resp.status_code == 404


async def test_records_page_renders_domains_and_records(admin_client, tmp_path, monkeypatch):
    """Unlike /records/count and the edit/delete actions, records_page also
    requires a matching DB Project row (selected_project) before it'll load
    JSONL data at all — not just a matching directory on disk."""
    from mulchd.config import settings
    from mulchd.models import Organization, Project

    monkeypatch.setattr(settings, "data_path", tmp_path)
    org = await Organization.create(slug="acme", display_name="Acme")
    await Project.create(slug="demo", display_name="Demo", org=org)
    expertise = tmp_path / "acme" / "demo" / ".mulch" / "expertise"
    expertise.mkdir(parents=True)
    (expertise / "architecture.jsonl").write_text(
        '{"id":"mx-aaa","type":"decision","classification":"tactical",'
        '"title":"Use Postgres","owner":"carlos","recorded_at":"2026-07-01T00:00:00+00:00"}\n'
    )
    resp = await admin_client.get("/admin/p/acme/demo/records")
    assert resp.status_code == 200
    assert "architecture" in resp.text
    assert "mx-aaa" in resp.text


async def test_delete_record_action_requires_auth(client):
    resp = await client.post(
        "/admin/records/delete",
        data={"project": "acme/demo", "domain": "architecture", "record_id": "mx-aaa"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_delete_record_action_calls_delete_record(admin_client, tmp_path, monkeypatch):
    import mulchd.admin.records_view as records_view
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    called = {}

    async def _fake_delete(m_dir, domain, record_id):
        called["args"] = (domain, record_id)

    monkeypatch.setattr(records_view, "delete_record", _fake_delete)

    resp = await admin_client.post(
        "/admin/records/delete",
        data={"project": "acme/demo", "domain": "architecture", "record_id": "mx-aaa"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/admin/p/acme/demo/records" in resp.headers["location"]
    assert called["args"] == ("architecture", "mx-aaa")


async def test_edit_record_action_requires_auth(client):
    resp = await client.post(
        "/admin/records/edit",
        data={
            "project": "acme/demo",
            "domain": "architecture",
            "record_id": "mx-aaa",
            "field": "content",
            "value": "new",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_edit_record_action_calls_edit_record(admin_client, tmp_path, monkeypatch):
    import mulchd.admin.records_view as records_view
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    called = {}

    async def _fake_edit(m_dir, domain, record_id, updates):
        called["args"] = (domain, record_id, updates)

    monkeypatch.setattr(records_view, "edit_record", _fake_edit)

    resp = await admin_client.post(
        "/admin/records/edit",
        data={
            "project": "acme/demo",
            "domain": "architecture",
            "record_id": "mx-aaa",
            "field": "content",
            "value": "  new content  ",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/admin/p/acme/demo/records" in resp.headers["location"]
    # value.strip() is applied before calling edit_record
    assert called["args"] == ("architecture", "mx-aaa", {"content": "new content"})


async def test_records_page_renders_select_checkboxes(admin_client, tmp_path, monkeypatch):
    from mulchd.config import settings
    from mulchd.models import Organization, Project

    monkeypatch.setattr(settings, "data_path", tmp_path)
    org = await Organization.create(slug="acme", display_name="Acme")
    await Project.create(slug="demo", display_name="Demo", org=org)
    expertise = tmp_path / "acme" / "demo" / ".mulch" / "expertise"
    expertise.mkdir(parents=True)
    (expertise / "architecture.jsonl").write_text(
        '{"id":"mx-aaa","type":"decision","classification":"tactical",'
        '"title":"Use Postgres","owner":"carlos","recorded_at":"2026-07-01T00:00:00+00:00"}\n'
    )
    resp = await admin_client.get("/admin/p/acme/demo/records")
    assert resp.status_code == 200
    assert 'class="record-select" data-domain="architecture" data-id="mx-aaa"' in resp.text


async def test_bulk_delete_records_action_requires_auth(client):
    resp = await client.post(
        "/admin/records/bulk-delete",
        data={"project": "acme/demo", "items": ['{"domain":"architecture","id":"mx-aaa"}']},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/connect" in resp.headers["location"]


async def test_bulk_delete_records_action_calls_delete_record_for_each_item(
    admin_client, tmp_path, monkeypatch
):
    import json

    import mulchd.admin.records_view as records_view
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    calls = []

    async def _fake_delete(m_dir, domain, record_id):
        calls.append((domain, record_id))

    monkeypatch.setattr(records_view, "delete_record", _fake_delete)

    resp = await admin_client.post(
        "/admin/records/bulk-delete",
        data={
            "project": "acme/demo",
            "items": [
                json.dumps({"domain": "architecture", "id": "mx-aaa"}),
                json.dumps({"domain": "ops", "id": "mx-bbb"}),
            ],
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/admin/p/acme/demo/records" in resp.headers["location"]
    assert calls == [("architecture", "mx-aaa"), ("ops", "mx-bbb")]


async def test_bulk_delete_records_action_skips_malformed_items(admin_client, tmp_path, monkeypatch):
    """Proves the JSON encoding survives a domain name containing characters
    a naive delimiter scheme would have mishandled (e.g. '::'), and that one
    bad item in the batch doesn't block the rest."""
    import json

    import mulchd.admin.records_view as records_view
    from mulchd.config import settings

    monkeypatch.setattr(settings, "data_path", tmp_path)
    calls = []

    async def _fake_delete(m_dir, domain, record_id):
        calls.append((domain, record_id))

    monkeypatch.setattr(records_view, "delete_record", _fake_delete)

    resp = await admin_client.post(
        "/admin/records/bulk-delete",
        data={
            "project": "acme/demo",
            "items": [
                "not valid json",
                json.dumps({"domain": "architecture"}),  # missing id
                json.dumps({"domain": "ops::weird", "id": "mx-ccc"}),  # unusual domain, still valid
                json.dumps({"domain": "architecture", "id": "mx-aaa"}),
            ],
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert calls == [("ops::weird", "mx-ccc"), ("architecture", "mx-aaa")]
