"""Invite-only sign-up: invite codes for new households and for household members."""
from datetime import datetime, timedelta, timezone

import pytest

from app.database import SessionLocal
from app.models import Invite, User
from conftest import PASSWORD, authed


@pytest.fixture
def invite_only(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "ALLOW_REGISTRATION", False)


def _register(client, username, code=None, household=None):
    body = {"username": username, "password": PASSWORD, "invite_code": code, "household_name": household}
    return client.post("/api/v1/auth/register", json=body)


def test_invite_only_blocks_strangers(make_user, anon_client, invite_only):
    # The very first account never needs an invite.
    assert anon_client.get("/api/v1/auth/bootstrap-status").json()["setup_required"] is True
    make_user("owner")
    status = anon_client.get("/api/v1/auth/bootstrap-status").json()
    assert status["invite_only"] is True and status["registration_open"] is False
    res = _register(anon_client, "stranger")
    assert res.status_code == 403
    assert "invitation" in res.json()["detail"]
    assert _register(anon_client, "guesser", code="AAAA-BBBB-CCCC").status_code == 400


def test_household_invite_creates_a_new_household(make_user, anon_client, invite_only):
    owner, owner_user = make_user("owner")
    res = owner.post("/api/v1/auth/invites", json={"kind": "household", "note": "For Mom"})
    assert res.status_code == 200, res.text
    invite = res.json()
    code = invite["code"]
    assert invite["status"] == "active" and invite["kind"] == "household" and invite["max_uses"] == 1

    check = anon_client.get("/api/v1/auth/invites/check", params={"code": code.lower().replace("-", "")}).json()
    assert check == {"valid": True, "kind": "household", "household_name": None, "expires_at": check["expires_at"]}

    res = _register(anon_client, "mom", code=code, household="Mom's House")
    assert res.status_code == 200, res.text
    mom = res.json()["user"]
    assert mom["household_id"] != owner_user["household_id"]
    assert mom["household_name"] == "Mom's House"
    assert mom["is_admin"] and not mom["is_superuser"]

    # Single use: the code is spent.
    assert _register(anon_client, "mom2", code=code).status_code == 400
    assert anon_client.get("/api/v1/auth/invites/check", params={"code": code}).json()["valid"] is False
    listed = owner.get("/api/v1/auth/invites").json()
    assert listed[0]["status"] == "used" and listed[0]["used_by"] == ["mom"] and listed[0]["note"] == "For Mom"
    # Only the hash is stored.
    with SessionLocal() as db:
        assert code not in db.query(Invite).one().code_hash


def test_member_invite_joins_the_household(make_user, anon_client, invite_only):
    admin, admin_user = make_user("admin_b")  # the first account: admin of its household
    res = admin.post("/api/v1/auth/invites", json={"kind": "member", "max_uses": 2, "expires_in_days": 3})
    assert res.status_code == 200, res.text
    code = res.json()["code"]
    assert res.json()["household_name"] == admin_user["household_name"]

    check = anon_client.get("/api/v1/auth/invites/check", params={"code": code}).json()
    assert check["kind"] == "member" and check["household_name"] == admin_user["household_name"]

    kid = _register(anon_client, "kid_one", code=code).json()["user"]
    assert kid["household_id"] == admin_user["household_id"] and kid["is_admin"] is False
    assert _register(anon_client, "kid_two", code=code).status_code == 200
    assert _register(anon_client, "kid_three", code=code).status_code == 400  # both uses spent
    names = {u["username"] for u in admin.get("/api/v1/auth/users").json()}
    assert names == {"admin_b", "kid_one", "kid_two"}


def test_invite_permissions_and_isolation(make_user, anon_client):
    owner, _ = make_user("owner")
    other_admin, _ = make_user("other_admin")
    # Only the instance owner invites new households.
    assert other_admin.post("/api/v1/auth/invites", json={"kind": "household"}).status_code == 403
    invite = owner.post("/api/v1/auth/invites", json={"kind": "member"}).json()
    # Another household can't see or revoke it.
    assert all(i["id"] != invite["id"] for i in other_admin.get("/api/v1/auth/invites").json())
    assert other_admin.delete(f"/api/v1/auth/invites/{invite['id']}").status_code == 404
    # Members who aren't admins can't manage invites.
    owner.post("/api/v1/auth/users", json={"username": "plain_member", "password": PASSWORD})
    token = anon_client.post("/api/v1/auth/login", json={"username": "plain_member", "password": PASSWORD}).json()["access_token"]
    member = authed(anon_client, token)
    assert member.get("/api/v1/auth/invites").status_code == 403
    assert member.post("/api/v1/auth/invites", json={"kind": "member"}).status_code == 403


def test_revoked_and_expired_invites_are_rejected(make_user, anon_client, invite_only):
    owner, _ = make_user("owner")
    revoked = owner.post("/api/v1/auth/invites", json={"kind": "household"}).json()
    assert owner.delete(f"/api/v1/auth/invites/{revoked['id']}").json()["status"] == "revoked"
    assert _register(anon_client, "late_one", code=revoked["code"]).status_code == 400

    expired = owner.post("/api/v1/auth/invites", json={"kind": "household"}).json()
    with SessionLocal() as db:
        db.get(Invite, expired["id"]).expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        db.commit()
    assert _register(anon_client, "late_two", code=expired["code"]).status_code == 400
    assert owner.get("/api/v1/auth/invites").json()[0]["status"] == "expired"
    with SessionLocal() as db:
        assert db.query(User).filter(User.username.in_(["late_one", "late_two"])).count() == 0


def test_owner_switches_registration_mode(make_user, anon_client, invite_only):
    owner, _ = make_user("owner")
    other, _ = make_user_with_invite(owner, anon_client)
    assert other.get("/api/v1/settings/registration").status_code == 403
    assert owner.get("/api/v1/settings/registration").json()["mode"] == "invite"
    assert owner.post("/api/v1/settings/registration", json={"mode": "open"}).json()["mode"] == "open"
    assert anon_client.get("/api/v1/auth/bootstrap-status").json()["registration_open"] is True
    assert _register(anon_client, "walk_in").status_code == 200
    owner.post("/api/v1/settings/registration", json={"mode": "invite"})
    assert _register(anon_client, "walk_in_two").status_code == 403


def make_user_with_invite(owner, anon_client):
    code = owner.post("/api/v1/auth/invites", json={"kind": "household"}).json()["code"]
    res = _register(anon_client.__class__(anon_client.app), "invited", code=code)
    body = res.json()
    return authed(anon_client.__class__(anon_client.app), body["access_token"]), body["user"]
