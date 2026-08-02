import pytest


async def test_activity_page_renders(admin_client):
    resp = await admin_client.get("/admin/activity")
    assert resp.status_code == 200
    assert "Activity" in resp.text


async def test_activity_page_shows_events(admin_client):
    from mulchd.instance_events import log_event
    from mulchd.models import InstanceEventCategory, Organization, Project, User

    admin = await User.get(username="admin")
    org = await Organization.create(slug="activityorg", display_name="Activity Org")
    project = await Project.create(slug="activityproj", display_name="Activity Proj", org=org)
    await log_event(
        InstanceEventCategory.PROJECT_CREATED, actor=admin, project=project
    )

    resp = await admin_client.get("/admin/activity")
    assert resp.status_code == 200
    assert "Created project activityorg/activityproj" in resp.text


async def test_activity_page_filters_by_category(admin_client):
    from mulchd.instance_events import log_event
    from mulchd.models import InstanceEventCategory, Organization, User

    admin = await User.get(username="admin")
    await log_event(InstanceEventCategory.ORG_CREATED, actor=admin, detail={"org_slug": "x"})
    org = await Organization.create(slug="filtertest", display_name="Filter Test")

    resp = await admin_client.get(
        f"/admin/activity?category={InstanceEventCategory.ORG_CREATED.value}"
    )
    assert resp.status_code == 200
    assert "Created org x" in resp.text
