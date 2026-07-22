import pytest

from mulchd.invite import matches_allowed_domains
from mulchd.models import InviteLink, InviteUse, Organization, Project, UserMembership


def test_null_patterns_accepts_any_email():
    assert matches_allowed_domains("alice@anywhere.com", None) is True


def test_empty_list_accepts_any_email():
    assert matches_allowed_domains("alice@anywhere.com", []) is True


def test_exact_domain_match():
    assert matches_allowed_domains("alice@company.com", ["company.com"]) is True


def test_exact_domain_no_match():
    assert matches_allowed_domains("alice@other.com", ["company.com"]) is False


def test_wildcard_single_subdomain():
    assert matches_allowed_domains("alice@ext.company.com", ["*.company.com"]) is True


def test_wildcard_deep_subdomain():
    assert matches_allowed_domains("alice@deep.ext.company.com", ["*.company.com"]) is True


def test_wildcard_does_not_match_bare_domain():
    assert matches_allowed_domains("alice@company.com", ["*.company.com"]) is False


def test_multiple_patterns_first_matches():
    assert matches_allowed_domains("alice@company.com", ["company.com", "*.company.com"]) is True


def test_multiple_patterns_second_matches():
    assert matches_allowed_domains("alice@ext.company.com", ["company.com", "*.company.com"]) is True


def test_multiple_patterns_none_match():
    assert matches_allowed_domains("alice@other.net", ["company.com", "*.company.com"]) is False


@pytest.fixture
async def invite_fixture(db):
    org = await Organization.create(slug="testorg", display_name="Test Org")
    project = await Project.create(slug="proj", display_name="Proj", org=org)
    invite = await InviteLink.create(
        token="validtoken123",
        project=project,
        role="writer",
    )
    return invite, project


async def test_invalid_token_returns_opaque_error(client, invite_fixture):
    resp = await client.get("/invite/doesnotexist")
    assert resp.status_code == 200
    assert "not valid" in resp.text


async def test_revoked_link_returns_opaque_error(client, invite_fixture, db):
    invite, _ = invite_fixture
    invite.revoked = True
    await invite.save()
    resp = await client.get(f"/invite/{invite.token}")
    assert resp.status_code == 200
    assert "not valid" in resp.text


async def test_valid_link_shows_login_page(client, invite_fixture):
    invite, project = invite_fixture
    resp = await client.get(f"/invite/{invite.token}")
    assert resp.status_code == 200
    assert project.display_name in resp.text


async def test_logged_in_user_claims_invite(client, invite_fixture, db):
    invite, project = invite_fixture
    from mulchd.auth import create_user
    from mulchd.connect import _signer

    user, _ = await create_user("claimuser", "Claim User", email="claim@company.com")
    signed = _signer().dumps(user.id)
    resp = await client.get(
        f"/invite/{invite.token}",
        cookies={"mulchd_connect": signed},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert await UserMembership.filter(user=user, project=project).exists()
    assert await InviteUse.filter(invite=invite, user=user).exists()
    await invite.refresh_from_db()
    assert invite.use_count == 1


async def test_already_member_skips_without_incrementing(client, invite_fixture, db):
    invite, project = invite_fixture
    from mulchd.auth import create_user
    from mulchd.connect import _signer
    from mulchd.models import Role

    user, _ = await create_user("existingmember", "Existing", email="existing@company.com")
    await UserMembership.create(user=user, project=project, role=Role.READER)
    signed = _signer().dumps(user.id)
    resp = await client.get(
        f"/invite/{invite.token}",
        cookies={"mulchd_connect": signed},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    await invite.refresh_from_db()
    assert invite.use_count == 0  # not incremented


async def test_token_login_with_pending_invite_claims(client, invite_fixture, db):
    """Token login while pending_invite in session claims the invite after auth."""
    invite, project = invite_fixture
    from mulchd.auth import create_user
    user, token = await create_user("tokeninvite", "Token Invite", email="ti@company.com")

    # Simulate session with pending invite (use client session cookie)
    # First hit the invite page to stash pending_invite
    resp = await client.get(f"/invite/{invite.token}")
    assert resp.status_code == 200

    # Now POST to /connect with the token — session cookie carries pending_invite
    resp = await client.post(
        "/connect",
        data={"token": token, "remember_me": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert await UserMembership.filter(user=user, project=project).exists()
    await invite.refresh_from_db()
    assert invite.use_count == 1


async def test_claim_invite_returns_false_when_exhausted(invite_fixture, db):
    from mulchd.auth import create_user
    from mulchd.invite import _claim_invite

    invite, project = invite_fixture
    invite.max_uses = 1
    await invite.save()

    first, _ = await create_user("first", "First", email="first@company.com")
    assert await _claim_invite(invite, first) is True

    second, _ = await create_user("second", "Second", email="second@company.com")
    assert await _claim_invite(invite, second) is False
    await invite.refresh_from_db()
    assert invite.use_count == 1


async def test_exhausted_link_returns_opaque_error(client, db):
    from mulchd.models import InviteLink, Organization, Project
    org = await Organization.create(slug="exhaustorg", display_name="E")
    project = await Project.create(slug="ep", display_name="EP", org=org)
    invite = await InviteLink.create(
        token="exhausted123",
        project=project,
        role="writer",
        max_uses=1,
        use_count=1,
    )
    resp = await client.get(f"/invite/{invite.token}")
    assert resp.status_code == 200
    assert "not valid" in resp.text


async def test_domain_restriction_blocks_wrong_email(client, db):
    from mulchd.auth import create_user
    from mulchd.connect import _signer
    from mulchd.models import InviteLink, Organization, Project
    org = await Organization.create(slug="domainorg", display_name="D")
    project = await Project.create(slug="dp", display_name="DP", org=org)
    invite = await InviteLink.create(
        token="domaintest123",
        project=project,
        role="writer",
        allowed_email_domains=["company.com"],
    )
    user, _ = await create_user("wrongdomain", "Wrong", email="user@other.net")
    signed = _signer().dumps(user.id)
    resp = await client.get(
        f"/invite/{invite.token}",
        cookies={"mulchd_connect": signed},
    )
    assert "not authorized" in resp.text
    assert not await UserMembership.filter(user=user, project=project).exists()


async def test_expired_link_returns_opaque_error(client, db):
    from datetime import UTC, datetime, timedelta
    from mulchd.models import InviteLink, Organization, Project
    org = await Organization.create(slug="expiredorg", display_name="EX")
    project = await Project.create(slug="exp", display_name="Exp", org=org)
    past = datetime.now(UTC) - timedelta(hours=1)
    invite = await InviteLink.create(
        token="expiredtoken123",
        project=project,
        role="writer",
        expires_at=past,
    )
    resp = await client.get(f"/invite/{invite.token}")
    assert "not valid" in resp.text


async def test_token_login_with_domain_restricted_invite_denies_silently_but_flags_it(client, db):
    """A pending invite with a domain restriction the user's email doesn't satisfy
    should not be claimed, and the login redirect should carry an invite_error hint."""
    from mulchd.auth import create_user
    from mulchd.models import InviteLink, Organization, Project, UserMembership
    org = await Organization.create(slug="domtok", display_name="DomTok")
    project = await Project.create(slug="dt", display_name="DT", org=org)
    invite = await InviteLink.create(
        token="domtoktoken123",
        project=project,
        role="writer",
        allowed_email_domains=["company.com"],
    )
    user, token = await create_user("domtokuser", "Dom Tok", email="user@other.net")

    resp = await client.get(f"/invite/{invite.token}")
    assert resp.status_code == 200

    resp = await client.post(
        "/connect",
        data={"token": token, "remember_me": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "invite_error=domain_denied" in resp.headers["location"]
    assert not await UserMembership.filter(user=user, project=project).exists()


async def test_claim_invite_logs_membership_added(db):
    from mulchd.auth import create_user
    from mulchd.invite import _claim_invite
    from mulchd.models import InstanceEvent, InstanceEventCategory, InviteLink, Organization, Project

    org = await Organization.create(slug="claimlogorg", display_name="Claim Log Org")
    project = await Project.create(slug="claimlogproj", display_name="Claim Log Proj", org=org)
    invite = await InviteLink.create(token="claimlogtoken", project=project, role="writer")
    user, _ = await create_user("claimloguser", "Claim Log User")

    result = await _claim_invite(invite, user)

    assert result is True
    event = await InstanceEvent.get(category=InstanceEventCategory.MEMBERSHIP_ADDED)
    assert event.actor_id == user.id
    assert event.subject_user_id == user.id
    assert event.project_id == project.id
    assert event.detail == {"role": "writer", "via": "invite"}


async def test_claim_invite_already_member_does_not_relog(db):
    from mulchd.auth import create_user
    from mulchd.invite import _claim_invite
    from mulchd.models import (
        InstanceEvent,
        InstanceEventCategory,
        InviteLink,
        Organization,
        Project,
        Role,
        UserMembership,
    )

    org = await Organization.create(slug="claimlogorg2", display_name="Claim Log Org 2")
    project = await Project.create(slug="claimlogproj2", display_name="Claim Log Proj 2", org=org)
    invite = await InviteLink.create(token="claimlogtoken2", project=project, role="writer")
    user, _ = await create_user("claimloguser2", "Claim Log User 2")
    await UserMembership.create(user=user, project=project, role=Role.WRITER)

    result = await _claim_invite(invite, user)

    assert result is True
    count = await InstanceEvent.filter(category=InstanceEventCategory.MEMBERSHIP_ADDED).count()
    assert count == 0


async def test_token_login_with_invalidated_pending_invite_flags_it(client, db):
    """If the pending invite gets revoked between visiting it and finishing login,
    the login redirect should carry an invite_error hint instead of silently succeeding."""
    from mulchd.auth import create_user
    from mulchd.models import InviteLink, Organization, Project, UserMembership
    org = await Organization.create(slug="revtok", display_name="RevTok")
    project = await Project.create(slug="rt", display_name="RT", org=org)
    invite = await InviteLink.create(
        token="revtoktoken123",
        project=project,
        role="writer",
    )
    user, token = await create_user("revtokuser", "Rev Tok", email="revtok@company.com")

    resp = await client.get(f"/invite/{invite.token}")
    assert resp.status_code == 200

    invite.revoked = True
    await invite.save()

    resp = await client.post(
        "/connect",
        data={"token": token, "remember_me": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "invite_error=invalid" in resp.headers["location"]
    assert not await UserMembership.filter(user=user, project=project).exists()
