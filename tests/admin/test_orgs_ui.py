import pytest


async def test_create_org(admin_client):
    resp = await admin_client.post(
        "/admin/orgs", data={"slug": "acme", "display_name": "Acme Corp"}, follow_redirects=False
    )
    assert resp.status_code == 303


async def test_create_org_logs_event(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory

    resp = await admin_client.post(
        "/admin/orgs",
        data={"slug": "logorg", "display_name": "Log Org"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    event = await InstanceEvent.get(category=InstanceEventCategory.ORG_CREATED)
    assert event.detail == {"org_slug": "logorg"}


async def test_create_org_duplicate_does_not_log(admin_client):
    from mulchd.models import InstanceEvent, InstanceEventCategory

    await admin_client.post("/admin/orgs", data={"slug": "duporg", "display_name": "Dup Org"})
    resp = await admin_client.post(
        "/admin/orgs",
        data={"slug": "duporg", "display_name": "Dup Org 2"},
        follow_redirects=False,
    )
    assert resp.status_code == 409

    count = await InstanceEvent.filter(category=InstanceEventCategory.ORG_CREATED).count()
    assert count == 1
