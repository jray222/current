from datetime import datetime, timedelta, timezone

import pyotp

from conftest import PASSWORD, authed


def test_first_user_is_owner_and_admin(make_user, anon_client):
    status = anon_client.get("/api/v1/auth/bootstrap-status").json()
    assert status == {"setup_required": True, "registration_open": True, "invite_only": False}

    _, owner = make_user("owner", "Smith Family")
    assert owner["is_admin"] and owner["is_superuser"]
    assert owner["household_name"] == "Smith Family"

    _, second = make_user("someone")
    assert second["is_admin"] and not second["is_superuser"]
    assert second["household_id"] != owner["household_id"]


def test_registration_closed(make_user, anon_client, monkeypatch):
    from app.config import settings
    make_user("owner")
    monkeypatch.setattr(settings, "ALLOW_REGISTRATION", False)
    res = anon_client.post("/api/v1/auth/register", json={"username": "late", "password": PASSWORD})
    assert res.status_code == 403


def test_weak_password_rejected(anon_client):
    res = anon_client.post("/api/v1/auth/register", json={"username": "weak", "password": "short"})
    assert res.status_code == 400


def test_login_lockout(make_user, anon_client):
    # More in test_signin_and_keys.py: known devices, doubling, the 2FA step.
    make_user("victim")
    for _ in range(5):
        assert anon_client.post("/api/v1/auth/login", json={"username": "victim", "password": "nope"}).status_code == 401
    res = anon_client.post("/api/v1/auth/login", json={"username": "victim", "password": PASSWORD})
    assert res.status_code == 401
    assert res.json() == {"detail": "Invalid username or password."}


def test_refresh_rotation_and_reuse_detection(make_user):
    client, _ = make_user("rotator")
    old_cookie = client.cookies.get("dose_refresh_token")
    res = client.post("/api/v1/auth/refresh")
    assert res.status_code == 200
    assert client.cookies.get("dose_refresh_token") != old_cookie

    # Replaying the old (rotated-out) token revokes the whole session family.
    # Clear the jar first: a second cookie of the same name can sit next to the
    # new one, and which of the two gets sent depends on the HTTP client version.
    client.cookies.clear()
    client.cookies.set("dose_refresh_token", old_cookie, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_password_change_invalidates_access_tokens(make_user, monkeypatch):
    client, _ = make_user("changer")
    # Record the password change a few seconds after the current token was issued.
    import app.routers.auth as auth_router
    real_now = auth_router._now
    monkeypatch.setattr(auth_router, "_now", lambda: real_now() + timedelta(seconds=5))

    res = client.post("/api/v1/auth/change-password",
                      json={"current_password": PASSWORD, "new_password": "Another-Strong-Pass-7"})
    assert res.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def _enable_2fa(client):
    setup = client.post("/api/v1/auth/2fa/setup").json()
    totp = pyotp.TOTP(setup["secret"])
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    totp.enrol_code = totp.now()
    confirm = client.post("/api/v1/auth/2fa/confirm", json={"code": totp.enrol_code})
    assert confirm.status_code == 200, confirm.text
    return totp, confirm.json()["backup_codes"]


def test_2fa_full_flow_with_replay_protection(make_user, anon_client):
    client, _ = make_user("secure")
    totp, backup_codes = _enable_2fa(client)
    assert len(backup_codes) == 10
    assert client.get("/api/v1/auth/me").json()["totp_enabled"] is True

    # Password alone is no longer enough.
    step1 = anon_client.post("/api/v1/auth/login", json={"username": "secure", "password": PASSWORD}).json()
    assert step1["mfa_required"] is True
    assert "access_token" not in step1
    # The MFA challenge token can't be used as an access token.
    assert authed(anon_client, step1["mfa_token"]).get("/api/v1/auth/me").status_code == 401
    anon_client.headers.pop("Authorization")

    # The code already used to confirm enrolment can't be replayed. Reuse that
    # exact code: a fresh totp.now() is a new code if a 30s step has passed.
    replay = anon_client.post("/api/v1/auth/login/verify-2fa", json={"mfa_token": step1["mfa_token"], "code": totp.enrol_code})
    assert replay.status_code == 401

    next_code = totp.at(datetime.now(timezone.utc) + timedelta(seconds=30))
    ok = anon_client.post("/api/v1/auth/login/verify-2fa", json={"mfa_token": step1["mfa_token"], "code": next_code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["username"] == "secure"


def test_backup_code_is_single_use(make_user, anon_client):
    client, _ = make_user("backup")
    _, backup_codes = _enable_2fa(client)
    code = backup_codes[0]

    def attempt():
        token = anon_client.post("/api/v1/auth/login", json={"username": "backup", "password": PASSWORD}).json()["mfa_token"]
        return anon_client.post("/api/v1/auth/login/verify-2fa", json={"mfa_token": token, "code": code})

    assert attempt().status_code == 200
    assert attempt().status_code == 401


def test_disable_2fa_requires_password_and_code(make_user):
    client, _ = make_user("disabler")
    totp, backup_codes = _enable_2fa(client)
    assert client.post("/api/v1/auth/2fa/disable", json={"password": "wrong", "code": backup_codes[0]}).status_code == 401
    assert client.post("/api/v1/auth/2fa/disable", json={"password": PASSWORD, "code": backup_codes[0]}).status_code == 200
    assert client.get("/api/v1/auth/me").json()["totp_enabled"] is False


def test_household_members_are_scoped(make_user):
    admin_a, user_a = make_user("admin_a")
    admin_b, _ = make_user("admin_b")

    res = admin_a.post("/api/v1/auth/users", json={"username": "spouse_a", "password": PASSWORD})
    assert res.status_code == 200
    assert res.json()["household_id"] == user_a["household_id"]

    names_a = {u["username"] for u in admin_a.get("/api/v1/auth/users").json()}
    names_b = {u["username"] for u in admin_b.get("/api/v1/auth/users").json()}
    assert names_a == {"admin_a", "spouse_a"}
    assert names_b == {"admin_b"}

    # B can't deactivate A's member.
    spouse_id = res.json()["id"]
    assert admin_b.delete(f"/api/v1/auth/users/{spouse_id}").status_code == 404


def test_non_admin_member_cannot_manage_users(make_user, anon_client):
    admin, _ = make_user("boss")
    admin.post("/api/v1/auth/users", json={"username": "kid", "password": PASSWORD})
    token = anon_client.post("/api/v1/auth/login", json={"username": "kid", "password": PASSWORD}).json()["access_token"]
    kid = authed(anon_client, token)
    assert kid.get("/api/v1/auth/users").status_code == 403


def test_ai_settings_owner_only_and_key_hidden_and_encrypted(make_user, monkeypatch):
    from app.config import settings
    from app.database import SessionLocal
    from app.models import RuntimeConfig
    owner, _ = make_user("owner")
    other, _ = make_user("other")
    assert other.get("/api/v1/settings/ai").status_code == 403
    assert other.post("/api/v1/settings/ai", json={"anthropic_api_key": "x"}).status_code == 403

    body = owner.get("/api/v1/settings/ai").json()
    assert body["anthropic_api_key_set"] is False and body["key_source"] is None

    assert owner.post("/api/v1/settings/ai", json={"anthropic_api_key": "sk-secret"}).status_code == 200
    body = owner.get("/api/v1/settings/ai").json()
    assert body["anthropic_api_key_set"] is True and body["key_source"] == "app"
    assert "sk-secret" not in str(body)
    with SessionLocal() as db:
        stored = db.query(RuntimeConfig).filter(RuntimeConfig.key == "anthropic_api_key").one().value
    assert stored.startswith("gAAAAA") and "sk-secret" not in stored

    # Sending no key keeps it; an empty one clears it.
    assert owner.post("/api/v1/settings/ai", json={"anthropic_model": "claude-sonnet-5-5"}).json()["anthropic_api_key_set"] is True
    assert owner.post("/api/v1/settings/ai", json={"anthropic_api_key": ""}).json()["anthropic_api_key_set"] is False

    # The environment is the fallback.
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-from-env")
    body = owner.get("/api/v1/settings/ai").json()
    assert body["anthropic_api_key_set"] is True and body["key_source"] == "environment"
    assert body["anthropic_model"] == "claude-sonnet-5-5"


