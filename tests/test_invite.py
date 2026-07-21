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
    past = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    invite = await InviteLink.create(
        token="expiredtoken123",
        project=project,
        role="writer",
        expires_at=past,
    )
    resp = await client.get(f"/invite/{invite.token}")
    assert "not valid" in resp.text
