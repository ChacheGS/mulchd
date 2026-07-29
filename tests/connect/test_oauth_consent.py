import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

from tests.connect.conftest import _authed_client

# ── OAuth consent ────────────────────────────────────────────────────────────


async def test_oauth_consent_redirects_to_login_when_unauthenticated(client, db):
    from mulchd.models import OAuthClient

    await OAuthClient.create(
        client_id="cli-a",
        client_metadata={"client_id": "cli-a", "redirect_uris": ["http://localhost/cb"], "client_name": "Cli A"},
    )
    resp = await client.get(
        "/connect/oauth-consent",
        params={
            "client_id": "cli-a",
            "redirect_uri": "http://localhost/cb",
            "code_challenge": "chal",
            "state": "st1",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/connect?return_to=")


async def test_oauth_consent_unknown_client_404s(client, alice_and_project):
    user, token, *_ = alice_and_project
    await _authed_client(client, token)
    resp = await client.get(
        "/connect/oauth-consent",
        params={
            "client_id": "does-not-exist",
            "redirect_uri": "http://localhost/cb",
            "code_challenge": "chal",
        },
    )
    assert resp.status_code == 404


async def test_oauth_consent_rejects_unregistered_redirect_uri(client, alice_and_project):
    from mulchd.models import OAuthClient

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    await OAuthClient.create(
        client_id="cli-evil-redirect",
        client_metadata={
            "client_id": "cli-evil-redirect",
            "redirect_uris": ["http://localhost/cb"],
            "client_name": "Legit Client",
        },
    )
    resp = await client.get(
        "/connect/oauth-consent",
        params={
            "client_id": "cli-evil-redirect",
            "redirect_uri": "https://evil.example/steal",
            "code_challenge": "chal",
            "state": "st-evil",
        },
    )
    assert resp.status_code == 400


async def test_oauth_consent_allow_rejects_unregistered_redirect_uri(client, alice_and_project):
    from mulchd.models import OAuthClient

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    await OAuthClient.create(
        client_id="cli-evil-redirect-2",
        client_metadata={
            "client_id": "cli-evil-redirect-2",
            "redirect_uris": ["http://localhost/cb"],
            "client_name": "Legit Client 2",
        },
    )
    resp = await client.post(
        "/connect/oauth-consent",
        data={
            "client_id": "cli-evil-redirect-2",
            "redirect_uri": "https://evil.example/steal",
            "code_challenge": "chal",
            "state": "st-evil2",
            "scope": "",
            "project_id": project.id,
            "decision": "allow",
        },
    )
    assert resp.status_code == 400


async def test_oauth_consent_page_shows_project_picker(client, alice_and_project):
    from mulchd.models import OAuthClient

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    await OAuthClient.create(
        client_id="cli-b",
        client_metadata={"client_id": "cli-b", "redirect_uris": ["http://localhost/cb"], "client_name": "Cli B"},
    )
    resp = await client.get(
        "/connect/oauth-consent",
        params={
            "client_id": "cli-b",
            "redirect_uri": "http://localhost/cb",
            "code_challenge": "chal",
            "state": "st2",
        },
    )
    assert resp.status_code == 200
    assert "Cli B" in resp.text
    assert project.display_name in resp.text


async def test_oauth_consent_deny_redirects_with_error(client, alice_and_project):
    from mulchd.models import OAuthClient

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    await OAuthClient.create(
        client_id="cli-c",
        client_metadata={"client_id": "cli-c", "redirect_uris": ["http://localhost/cb"], "client_name": "Cli C"},
    )
    resp = await client.post(
        "/connect/oauth-consent",
        data={
            "client_id": "cli-c",
            "redirect_uri": "http://localhost/cb",
            "code_challenge": "chal",
            "state": "st3",
            "scope": "",
            "decision": "deny",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "error=access_denied" in resp.headers["location"]
    assert "state=st3" in resp.headers["location"]


async def test_oauth_consent_allow_creates_grant_and_redirects_with_code(client, alice_and_project):
    from mulchd.models import OAuthClient, OAuthGrant

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    await OAuthClient.create(
        client_id="cli-d",
        client_metadata={"client_id": "cli-d", "redirect_uris": ["http://localhost/cb"], "client_name": "Cli D"},
    )
    resp = await client.post(
        "/connect/oauth-consent",
        data={
            "client_id": "cli-d",
            "redirect_uri": "http://localhost/cb",
            "code_challenge": "chal",
            "state": "st4",
            "scope": "",
            "project_id": project.id,
            "decision": "allow",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("http://localhost/cb?")
    assert "code=" in location
    assert "state=st4" in location
    assert await OAuthGrant.filter(user=user, project=project).exists()

    from mulchd.models import OAuthCode

    # OAuthCode.client_id must be the OAuthClient's string client_id ("cli-d"), not
    # the related row's integer primary key — regression test for a bug where
    # _issue_oauth_code derived it from grant.client_id (Tortoise's raw FK column,
    # an int) instead of the caller's already-loaded OAuthClient.client_id string.
    code_row = await OAuthCode.filter(grant__user=user, grant__project=project).first()
    assert code_row is not None
    assert code_row.client_id == "cli-d"


async def test_oauth_consent_allow_nonexistent_project_returns_403(client, alice_and_project):
    from mulchd.models import OAuthClient, OAuthGrant

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    await OAuthClient.create(
        client_id="cli-noproj",
        client_metadata={"client_id": "cli-noproj", "redirect_uris": ["http://localhost/cb"], "client_name": "Cli NoProj"},
    )
    resp = await client.post(
        "/connect/oauth-consent",
        data={
            "client_id": "cli-noproj",
            "redirect_uri": "http://localhost/cb",
            "code_challenge": "chal",
            "state": "st-noproj",
            "scope": "",
            "project_id": 999999,
            "decision": "allow",
        },
    )
    assert resp.status_code == 403
    assert not await OAuthGrant.filter(user=user).exists()


async def test_oauth_consent_allow_non_member_project_returns_403(client, alice_and_project):
    from mulchd.models import OAuthClient, OAuthGrant, Organization, Project

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    other_org = await Organization.create(slug="other-org", display_name="Other Org")
    other_project = await Project.create(slug="other-proj", display_name="Other Proj", org=other_org)
    await OAuthClient.create(
        client_id="cli-notmember",
        client_metadata={
            "client_id": "cli-notmember",
            "redirect_uris": ["http://localhost/cb"],
            "client_name": "Cli NotMember",
        },
    )
    resp = await client.post(
        "/connect/oauth-consent",
        data={
            "client_id": "cli-notmember",
            "redirect_uri": "http://localhost/cb",
            "code_challenge": "chal",
            "state": "st-notmember",
            "scope": "",
            "project_id": other_project.id,
            "decision": "allow",
        },
    )
    assert resp.status_code == 403
    assert not await OAuthGrant.filter(user=user).exists()


async def test_oauth_consent_allow_second_time_skips_picker(client, alice_and_project):
    """An existing grant for (client, user) issues a code immediately, no form."""
    from mulchd.models import OAuthClient, OAuthGrant

    user, token, org, project = alice_and_project
    await _authed_client(client, token)
    oc = await OAuthClient.create(
        client_id="cli-e",
        client_metadata={"client_id": "cli-e", "redirect_uris": ["http://localhost/cb"], "client_name": "Cli E"},
    )
    await OAuthGrant.create(client=oc, user=user, project=project)

    resp = await client.get(
        "/connect/oauth-consent",
        params={
            "client_id": "cli-e",
            "redirect_uri": "http://localhost/cb",
            "code_challenge": "chal",
            "state": "st5",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("http://localhost/cb?")
    assert "code=" in resp.headers["location"]

    from mulchd.models import OAuthCode

    code_row = await OAuthCode.filter(grant__user=user, grant__project=project).first()
    assert code_row is not None
    assert code_row.client_id == "cli-e"


async def test_oauth_consent_login_round_trip_returns_to_pending_authorization(
    client, alice_and_project
):
    """Unauthenticated consent hit -> follow to /connect?return_to=... -> log in ->
    land back on the original oauth-consent URL, not /connect/projects."""
    from mulchd.models import OAuthClient

    user, token, org, project = alice_and_project
    await OAuthClient.create(
        client_id="cli-f",
        client_metadata={"client_id": "cli-f", "redirect_uris": ["http://localhost/cb"], "client_name": "Cli F"},
    )

    consent_resp = await client.get(
        "/connect/oauth-consent",
        params={
            "client_id": "cli-f",
            "redirect_uri": "http://localhost/cb",
            "code_challenge": "chal",
            "state": "st6",
        },
        follow_redirects=False,
    )
    assert consent_resp.status_code == 303
    login_location = consent_resp.headers["location"]
    assert login_location.startswith("/connect?return_to=")

    await client.get(login_location, follow_redirects=False)

    login_resp = await client.post(
        "/connect", data={"token": token, "remember_me": ""}, follow_redirects=False
    )
    assert login_resp.status_code == 303
    final_location = login_resp.headers["location"]
    assert final_location.startswith("/connect/oauth-consent?")
    assert "client_id=cli-f" in final_location
    assert "state=st6" in final_location


def test_safe_return_to_rejects_literal_scheme_but_allows_encoded_redirect_uri():
    from mulchd.connect import _safe_return_to

    encoded = "/connect/oauth-consent?redirect_uri=http%3A%2F%2Flocalhost%2Fcb"
    assert _safe_return_to(encoded) == encoded

    literal = "/connect/oauth-consent?redirect_uri=http://localhost/cb"
    assert _safe_return_to(literal) is None
