"""Sign-in lockout with known devices (services/lockout.py), where visitor
addresses come from behind a proxy (deps.get_client_ip), and the server's keys
(services/keys.py)."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pyotp
import pytest
from cryptography.fernet import Fernet, InvalidToken

from app import cli
from app.config import settings
from app.database import SessionLocal
from app.deps import get_client_ip
from app.models import LoginAuditLog, RuntimeConfig, User
from app.rate_limit import auth_rate_limiter
from app.security import decrypt_secret, encrypt_secret, key_state, legacy_data_key
from app.services import ai, keys, lockout

from conftest import PASSWORD, _client, authed

LOGIN = "/api/v1/auth/login"
WRONG = "Wrong-Password-123!"
REFUSED = {"detail": "Invalid username or password."}


def _login(client, username, password=PASSWORD):
    return client.post(LOGIN, json={"username": username, "password": password})


def _fail(client, username, times=5):
    for _ in range(times):
        res = _login(client, username, WRONG)
        assert res.status_code == 401 and res.json() == REFUSED


def _user(username) -> User:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        db.expunge(user)
        return user


# ---------------------------------------------------------------- lockout

def test_wrong_passwords_pause_new_devices_but_not_the_owners_own(make_user, anon_client):
    owner, _ = make_user("victim")  # signing up makes this browser a known device
    _fail(anon_client, "victim")

    # The right password from a new device is refused, exactly like a wrong one.
    assert _login(anon_client, "victim").json() == REFUSED
    assert _login(_client(), "victim").status_code == 401

    # The owner's own browser still signs in, and isn't told anything alarming about itself.
    res = _login(owner, "victim")
    assert res.status_code == 200, res.text
    assert res.json()["failed_attempts"]["count"] == 7
    # ...and that didn't hand the guesser a fresh 5 tries.
    assert _login(anon_client, "victim").status_code == 401


def test_every_refusal_looks_the_same(make_user, anon_client):
    owner, _ = make_user("owner")
    owner.post("/api/v1/auth/users", json={"username": "leaver", "password": PASSWORD})
    leaver = _user("leaver")
    owner.delete(f"/api/v1/auth/users/{leaver.id}")
    make_user("paused")
    _fail(anon_client, "paused")
    auth_rate_limiter.reset()

    answers = [
        _login(anon_client, "nobody-by-this-name"),
        _login(anon_client, "owner", WRONG),
        _login(anon_client, "paused"),  # right password, paused
        _login(anon_client, "leaver"),  # right password, deactivated
    ]
    assert {(r.status_code, r.text) for r in answers} == {(401, json.dumps(REFUSED, separators=(",", ":")))}
    assert all(r.status_code != 423 for r in answers)


def test_pauses_double_up_to_a_day_and_a_sign_in_resets_them():
    record = lockout._DeviceRecord()
    now = datetime(2026, 10, 1, 8, tzinfo=timezone.utc)
    pauses = []
    for _ in range(9):
        for i in range(5):
            started = lockout._count_failure(record, now)
            assert started == (i == 4)
        pauses.append(record.locked_until - now)
        now = record.locked_until + timedelta(minutes=1)  # the guesser waits it out and tries again
    assert pauses[:4] == [timedelta(minutes=m) for m in (15, 30, 60, 120)]
    assert pauses[-1] == timedelta(hours=24) and max(pauses) == timedelta(hours=24)

    # Failures spread out more than 15 minutes apart never add up.
    record = lockout._DeviceRecord()
    for i in range(10):
        assert not lockout._count_failure(record, now + timedelta(minutes=16 * i))

    # A quiet day after the last pause ends forgets the doubling.
    record = lockout._DeviceRecord()
    for _ in range(10):
        lockout._count_failure(record, now)
    assert record.lockout_level == 2
    later = record.locked_until + timedelta(hours=25)
    for _ in range(5):
        lockout._count_failure(record, later)
    assert record.locked_until - later == timedelta(minutes=15)


def test_a_paused_new_device_signs_in_once_the_pause_ends(make_user, anon_client, monkeypatch):
    make_user("waiter")
    _fail(anon_client, "waiter")
    assert _user("waiter").lockout_level == 1
    real_now = lockout._now
    monkeypatch.setattr(lockout, "_now", lambda: real_now() + timedelta(minutes=16))
    res = _login(anon_client, "waiter")
    assert res.status_code == 200
    user = _user("waiter")
    assert user.locked_until is None and user.lockout_level == 0 and user.failed_login_attempts == 0


def test_wrong_passwords_on_a_known_device_pause_only_that_device(make_user):
    phone, _ = make_user("careless")
    _fail(phone, "careless")
    assert _login(phone, "careless").status_code == 401  # this browser is paused...
    laptop = _client()
    assert _login(laptop, "careless").status_code == 200  # ...a new one isn't, nor the account
    assert _user("careless").locked_until is None


def test_known_device_cookie_belongs_to_one_account(make_user, anon_client):
    make_user("first")
    second, _ = make_user("second")
    _fail(anon_client, "first")
    # "second"'s cookie is no use for "first", and a forged one isn't either.
    assert _login(second, "first").status_code == 401
    second.cookies.set(lockout.cookie_name(_user("first").id), "not-a-real-token", path="/api/v1/auth")
    assert _login(second, "first").status_code == 401


def _enable_2fa(client):
    setup = client.post("/api/v1/auth/2fa/setup").json()
    totp = pyotp.TOTP(setup["secret"])
    res = client.post("/api/v1/auth/2fa/confirm", json={"code": totp.now()})
    assert res.status_code == 200
    return totp, res.json()["backup_codes"]


def test_wrong_2fa_codes_count_and_never_say_locked(make_user, anon_client):
    owner, _ = make_user("twofa")
    totp, _ = _enable_2fa(owner)
    mfa_token = _login(anon_client, "twofa").json()["mfa_token"]
    for _ in range(5):
        res = anon_client.post("/api/v1/auth/login/verify-2fa", json={"mfa_token": mfa_token, "code": "000000"})
        assert res.status_code == 401 and res.json() == {"detail": "Invalid authentication code."}
    res = anon_client.post("/api/v1/auth/login/verify-2fa", json={"mfa_token": mfa_token, "code": totp.now()})
    assert res.status_code == 401 and res.json() == {"detail": "Invalid authentication code."}
    # The password step is paused for new devices now too.
    assert _login(anon_client, "twofa").json() == REFUSED
    # The owner's browser gets through both steps.
    mfa_token = _login(owner, "twofa").json()["mfa_token"]
    with SessionLocal() as db:  # the confirm step used the current code
        db.query(User).filter(User.username == "twofa").update({"totp_last_used_step": None})
        db.commit()
    res = owner.post("/api/v1/auth/login/verify-2fa", json={"mfa_token": mfa_token, "code": totp.now()})
    assert res.status_code == 200, res.text
    assert res.json()["failed_attempts"]["count"] >= 6


def test_failed_attempts_notice_counts_since_the_last_visit(make_user, anon_client):
    owner, _ = make_user("noticed")
    _fail(anon_client, "noticed", times=3)
    with SessionLocal() as db:
        db.add(LoginAuditLog(user_id=_user("noticed").id, event="login_failed_bad_password", ip_address="198.51.100.9"))
        db.commit()
    res = _login(owner, "noticed")
    assert res.json()["failed_attempts"]["count"] == 4
    assert res.json()["failed_attempts"]["addresses"] == 2
    assert _login(owner, "noticed").json()["failed_attempts"] is None


def test_admins_clear_a_lock(make_user, anon_client):
    admin, _ = make_user("admin", "Family")
    admin.post("/api/v1/auth/users", json={"username": "kid", "password": PASSWORD})
    kid_id = _user("kid").id
    _fail(anon_client, "kid")
    listed = {u["username"]: u for u in admin.get("/api/v1/auth/users").json()}
    assert listed["kid"]["locked_until"] is not None

    other_admin, _ = make_user("neighbor")
    assert other_admin.post(f"/api/v1/auth/users/{kid_id}/clear-lock").status_code == 404

    res = admin.post(f"/api/v1/auth/users/{kid_id}/clear-lock")
    assert res.status_code == 200 and res.json()["locked_until"] is None
    assert _login(anon_client, "kid").status_code == 200


def test_members_cannot_clear_locks(make_user, anon_client):
    admin, _ = make_user("admin")
    admin.post("/api/v1/auth/users", json={"username": "member", "password": PASSWORD})
    member = authed(_client(), _login(_client(), "member").json()["access_token"])
    assert member.post(f"/api/v1/auth/users/{_user('admin').id}/clear-lock").status_code == 403


def test_server_command_clears_a_lock(make_user, anon_client, capsys):
    make_user("stuck")
    _fail(anon_client, "stuck")
    assert cli.main(["clear-lock", "stuck"]) == 0
    assert "can sign in from new devices again" in capsys.readouterr().out
    assert _login(anon_client, "stuck").status_code == 200
    assert cli.main(["clear-lock", "nobody"]) == 1


# ---------------------------------------------------------------- visitor addresses

def _request(headers, host):
    return SimpleNamespace(headers={k.lower(): v for k, v in headers.items()}, client=SimpleNamespace(host=host))


@pytest.mark.parametrize("peer, headers, expected", [
    # Port open to the internet: whoever connects can't claim to be someone else.
    ("203.0.113.50", {"CF-Connecting-IP": "198.51.100.1"}, "203.0.113.50"),
    ("203.0.113.50", {"X-Forwarded-For": "198.51.100.1"}, "203.0.113.50"),
    # Through Cloudflare's own addresses, or a tunnel/proxy on the Docker network.
    ("104.16.10.20", {"CF-Connecting-IP": "198.51.100.1"}, "198.51.100.1"),
    ("2606:4700::6810:1", {"CF-Connecting-IP": "2001:db8::7"}, "2001:db8::7"),
    ("::ffff:172.18.0.3", {"X-Real-IP": "198.51.100.2"}, "198.51.100.2"),
    # A made-up hop in front of the real one is ignored.
    ("172.18.0.3", {"X-Forwarded-For": "1.2.3.4, 198.51.100.7, 172.18.0.9"}, "198.51.100.7"),
    ("172.18.0.3", {"CF-Connecting-IP": "not an address", "X-Forwarded-For": "198.51.100.8"}, "198.51.100.8"),
    ("172.18.0.3", {}, "172.18.0.3"),
])
def test_forwarded_addresses_only_from_proxies(monkeypatch, peer, headers, expected):
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    assert get_client_ip(_request(headers, peer)) == expected


def test_trusted_proxies_adds_an_outside_proxy(monkeypatch):
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    request = _request({"X-Forwarded-For": "198.51.100.1"}, "203.0.113.50")
    assert get_client_ip(request) == "203.0.113.50"
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "203.0.113.48/28, nonsense")
    assert get_client_ip(request) == "198.51.100.1"


# ---------------------------------------------------------------- keys

NEW_KEY = Fernet.generate_key().decode()
OTHER_KEY = Fernet.generate_key().decode()


def _encrypted_everything(owner):
    """One of every encrypted value Dose stores."""
    _, backup_codes = _enable_2fa(owner)
    assert owner.post("/api/v1/settings/ai", json={"anthropic_api_key": "sk-ant-test-key"}).status_code == 200
    with SessionLocal() as db:
        keys.load(db)
    return backup_codes


def _all_values(db):
    seen = []
    keys._visit(db, lambda value, what: seen.append((what, value)))
    return seen


def test_rotation_moves_every_value_to_the_newest_key(make_user, monkeypatch):
    owner, user = make_user("owner")
    _encrypted_everything(owner)
    before = owner.get("/api/v1/settings/keys").json()
    assert before["data_keys"] == [] and before["legacy"]["values"] == 3
    assert any("made from the sign-in key" in a for a in before["advice"])

    monkeypatch.setattr(settings, "DATA_KEYS", f"{NEW_KEY}")
    middle = owner.get("/api/v1/settings/keys").json()
    assert middle["data_keys"][0]["values"] == 0 and middle["legacy"]["values"] == 3
    assert any("older key" in a for a in middle["advice"])

    assert owner.post("/api/v1/settings/keys/rotate", json={"password": "nope"}).status_code == 401
    res = owner.post("/api/v1/settings/keys/rotate", json={"password": PASSWORD})
    assert res.status_code == 200, res.text
    assert res.json()["moved"] == 3 and res.json()["skipped"] == []
    after = res.json()["keys"]
    assert after["data_keys"][0]["values"] == 3 and after["legacy"] == {"retired": True, "values": 0}

    with SessionLocal() as db:
        values = _all_values(db)
        assert {what for what, _ in values} == {"2FA secret", "Anthropic API key", "key check"}
        for what, value in values:
            Fernet(NEW_KEY.encode()).decrypt(value.encode())  # the new key opens every one
            with pytest.raises(InvalidToken):
                Fernet(legacy_data_key()).decrypt(value.encode())

    # From now on SECRET_KEY can change without losing anything.
    monkeypatch.setattr(settings, "SECRET_KEY", "a-completely-different-signing-key-" + "y" * 40)
    with SessionLocal() as db:
        keys.load(db)
        assert key_state.problem is None
        assert ai.runtime_settings(db)["anthropic_api_key"] == "sk-ant-test-key"


def test_rotation_needs_a_data_key_and_the_owner(make_user):
    owner, _ = make_user("owner")
    member, _ = make_user("someone")
    res = owner.post("/api/v1/settings/keys/rotate", json={"password": PASSWORD})
    assert res.status_code == 400 and "DATA_KEYS" in res.json()["detail"]
    assert member.post("/api/v1/settings/keys/rotate", json={"password": PASSWORD}).status_code == 403
    assert member.get("/api/v1/settings/keys").status_code == 403


def test_older_data_keys_still_open_values_until_removed(make_user, monkeypatch):
    owner, user = make_user("owner")
    monkeypatch.setattr(settings, "DATA_KEYS", OTHER_KEY)
    with SessionLocal() as db:
        keys.load(db)
        value = encrypt_secret("made with the old data key")
    monkeypatch.setattr(settings, "DATA_KEYS", f"{NEW_KEY}, {OTHER_KEY}")
    assert decrypt_secret(value) == "made with the old data key"
    assert encrypt_secret("x") and Fernet(NEW_KEY.encode()).decrypt(encrypt_secret("x").encode()) == b"x"
    owner.post("/api/v1/settings/keys/rotate", json={"password": PASSWORD})
    described = owner.get("/api/v1/settings/keys").json()
    assert [k["values"] for k in described["data_keys"]] == [1, 0]  # the key check
    assert any("remove them from DATA_KEYS" in a for a in described["advice"])


def test_a_changed_key_is_reported_not_silent(make_user, monkeypatch):
    owner, user = make_user("owner")
    hid = user["household_id"]
    backup_codes = _encrypted_everything(owner)
    with SessionLocal() as db:
        keys.load(db)
        assert key_state.problem is None

    # The volume's key file was lost, or SECRET_KEY was retyped.
    monkeypatch.setattr(settings, "SECRET_KEY", "a-completely-different-signing-key-" + "z" * 40)
    with SessionLocal() as db:
        keys.load(db)
        assert key_state.problem == "changed"
        alert = keys.alerts(db)[0]
        assert alert["kind"] == "key_changed" and not alert["dismissible"] and alert["action"] == "keys"

    # Sign-ins were signed with the old key too. 2FA codes can't be checked any
    # more (the secret is unreadable), but backup codes still work.
    assert owner.get("/api/v1/auth/me").status_code == 401
    mfa_token = _login(owner, "owner").json()["mfa_token"]
    res = owner.post("/api/v1/auth/login/verify-2fa", json={"mfa_token": mfa_token, "code": backup_codes[0]})
    assert res.status_code == 200, res.text
    owner = authed(owner, res.json()["access_token"])
    assert owner.get("/api/v1/settings/keys").json()["problem"] == "changed"
    assert owner.post("/api/v1/settings/keys/rotate", json={"password": PASSWORD}).status_code == 400
    res = owner.post("/api/v1/settings/keys/accept", json={"password": PASSWORD})
    assert res.status_code == 200, res.text
    assert len(res.json()["unreadable"]) == 2  # left alone, in case the old key turns up
    assert key_state.problem is None
    assert owner.get("/api/v1/settings/keys").json()["problem"] is None


def test_a_typo_in_data_keys_is_flagged(make_user, monkeypatch):
    owner, _ = make_user("owner")
    monkeypatch.setattr(settings, "DATA_KEYS", f"not-a-key, {NEW_KEY}")
    described = owner.get("/api/v1/settings/keys").json()
    assert described["invalid_data_keys"] == 1 and len(described["data_keys"]) == 1
    assert "keys:invalid" in {a["key"] for a in keys.alerts(SessionLocal())}
    assert Fernet(NEW_KEY.encode()).decrypt(encrypt_secret("still works").encode()) == b"still works"


def test_a_plain_anthropic_key_is_encrypted_at_startup(make_user):
    owner, _ = make_user("owner")
    with SessionLocal() as db:
        db.add(RuntimeConfig(key="anthropic_api_key", value="sk-ant-stored-in-plain-text"))
        db.commit()
        assert ai.runtime_settings(db)["anthropic_api_key"] == "sk-ant-stored-in-plain-text"
        keys.load(db)
        stored = db.query(RuntimeConfig).filter(RuntimeConfig.key == "anthropic_api_key").one().value
        assert stored.startswith("gAAAAA") and "sk-ant" not in stored
        assert ai.runtime_settings(db)["anthropic_api_key"] == "sk-ant-stored-in-plain-text"
    assert owner.get("/api/v1/settings/ai").json()["anthropic_api_key_set"] is True


def test_key_screen_shows_where_keys_live_but_never_the_keys(make_user, monkeypatch):
    owner, _ = make_user("owner")
    monkeypatch.setattr(settings, "DATA_KEYS", NEW_KEY)
    with SessionLocal() as db:
        keys.load(db)
    res = owner.get("/api/v1/settings/keys")
    body = res.json()
    assert body["signing_key"]["source"] == "environment"
    assert body["signing_key"]["first_seen"] == datetime.now(timezone.utc).date().isoformat()
    assert len(body["signing_key"]["fingerprint"]) == 14
    assert settings.SECRET_KEY not in res.text and NEW_KEY not in res.text
    assert legacy_data_key().decode() not in res.text


def test_sign_everyone_out(make_user, monkeypatch):
    owner, _ = make_user("owner")
    member, _ = make_user("someone")
    assert member.post("/api/v1/settings/keys/sign-out-everyone", json={"password": PASSWORD}).status_code == 403
    assert owner.post("/api/v1/settings/keys/sign-out-everyone", json={"password": "nope"}).status_code == 401
    assert owner.post("/api/v1/settings/keys/sign-out-everyone", json={"password": PASSWORD}).status_code == 200
    for client in (owner, member):
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.post("/api/v1/auth/refresh").status_code == 401

    # Signing in again afterwards works, and the cut-off survives a restart.
    token = _login(owner, "owner").json()["access_token"]
    assert authed(owner, token).get("/api/v1/auth/me").status_code == 200
    key_state.sessions_generation = 0
    with SessionLocal() as db:
        keys.load(db)
    assert key_state.sessions_generation == 1
    assert authed(owner, token).get("/api/v1/auth/me").status_code == 200
    assert authed(member, member.headers["Authorization"].split()[1]).get("/api/v1/auth/me").status_code == 401
    assert owner.get("/api/v1/settings/keys").json()["signed_everyone_out_at"] is not None
