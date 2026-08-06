"""
Policies section on the project Overview page.
"""

from mulchd.models import Organization, Project


async def test_overview_shows_policy_defaults(admin_client):
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)

    resp = await admin_client.get(f"/admin/p/{org.slug}/{project.slug}/")
    assert resp.status_code == 200
    assert "guardrail_enforcement" in resp.text
    assert "code default" in resp.text


async def test_overview_shows_env_default_source(admin_client, monkeypatch):
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    monkeypatch.setenv("MULCHD_POLICY_STRICT_DOMAINS", "true")

    resp = await admin_client.get(f"/admin/p/{org.slug}/{project.slug}/")
    assert "env default" in resp.text


async def test_overview_shows_locked_and_disables_control(admin_client, monkeypatch):
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    monkeypatch.setenv("MULCHD_POLICY_STRICT_DOMAINS", "ro:true")

    resp = await admin_client.get(f"/admin/p/{org.slug}/{project.slug}/")
    assert "locked by MULCHD_POLICY_STRICT_DOMAINS" in resp.text
    assert "disabled" in resp.text

    # Isolate the strict_domains policy's own <form>...</form> block and
    # confirm its Save button is genuinely absent, not just that "disabled"
    # appears somewhere else on the page.
    form_start = resp.text.index('policies/strict_domains"')
    form_end = resp.text.index("</form>", form_start)
    strict_domains_form = resp.text[form_start:form_end]
    assert "disabled" in strict_domains_form
    assert 'type="submit"' not in strict_domains_form


async def test_set_policy_creates_override(admin_client):
    from mulchd.models import ProjectPolicy

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)

    resp = await admin_client.post(
        f"/admin/p/{org.slug}/{project.slug}/policies/default_page_size",
        data={"value": "25"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    row = await ProjectPolicy.get(project=project, key="default_page_size")
    assert row.value == [25]


async def test_set_policy_redirect_shows_fresh_value(admin_client):
    """The PRG redirect after a successful write must reflect the write
    immediately, not a value cached by the earlier lock-check call within the
    same request (see resolve_policy's TTL override cache)."""
    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)

    resp = await admin_client.post(
        f"/admin/p/{org.slug}/{project.slug}/policies/default_page_size",
        data={"value": "25"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "overridden" in resp.text
    assert 'value="25"' in resp.text


async def test_set_policy_rejects_invalid_value(admin_client):
    from mulchd.models import ProjectPolicy

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)

    resp = await admin_client.post(
        f"/admin/p/{org.slug}/{project.slug}/policies/default_page_size",
        data={"value": "notanumber"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert await ProjectPolicy.get_or_none(project=project, key="default_page_size") is None


async def test_set_policy_rejected_when_locked(admin_client, monkeypatch):
    from mulchd.models import ProjectPolicy

    org = await Organization.create(slug="acme", display_name="Acme Corp")
    project = await Project.create(slug="infra", display_name="Infrastructure", org=org)
    monkeypatch.setenv("MULCHD_POLICY_STRICT_DOMAINS", "ro:true")

    resp = await admin_client.post(
        f"/admin/p/{org.slug}/{project.slug}/policies/strict_domains",
        data={"value": "false"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert await ProjectPolicy.get_or_none(project=project, key="strict_domains") is None
