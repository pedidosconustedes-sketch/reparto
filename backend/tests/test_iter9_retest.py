# Iteration 9: retest of iteration 8 fixes (atomic lockout, business account reset -> auth_version bump + unlock, change-password errors, photo-token)
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from pymongo import MongoClient

API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
_mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB = _mc[os.environ.get("DB_NAME", "test_database")]


def _unlock_all():
    DB.users.update_many({}, {"$set": {"failed_logins": 0, "locked_until": None}})


@pytest.fixture(scope="module")
def owner_h():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30)
    assert r.status_code == 200, r.text
    yield {"Authorization": f"Bearer {r.json()['token']}"}
    _unlock_all()


@pytest.fixture
def temp_courier(owner_h):
    phone = "18" + str(uuid.uuid4().int)[:8]
    r = requests.post(f"{API}/couriers", headers=owner_h, json={"name": "TEST_Race9", "phone": phone, "pin": "111111", "vehicle": "moto"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    cid = r.json()["id"]
    yield phone
    requests.delete(f"{API}/couriers/{cid}", headers=owner_h, timeout=30)


@pytest.fixture
def temp_biz(owner_h):
    r = requests.post(f"{API}/businesses", headers=owner_h, json={"name": "TEST_Biz9", "address": "Av. Corrientes 1234, Buenos Aires", "phone": "1100000099"}, timeout=60)
    assert r.status_code in (200, 201), r.text
    bid = r.json()["id"]
    email = f"test_biz9_{uuid.uuid4().hex[:6]}@delivery.com"
    r = requests.put(f"{API}/businesses/{bid}/account", headers=owner_h, json={"email": email, "password": "BizPass111"}, timeout=30)
    assert r.status_code == 200, r.text
    yield bid, email
    requests.delete(f"{API}/businesses/{bid}", headers=owner_h, timeout=30)


def _courier_login(phone, pin):
    return requests.post(f"{API}/auth/courier/login", json={"phone": phone, "pin": pin}, timeout=60).status_code


# Lockout: 20 parallel wrong PINs must lock the account
def test_parallel_wrong_pins_lock_account(temp_courier):
    with ThreadPoolExecutor(20) as ex:
        codes = list(ex.map(lambda i: _courier_login(temp_courier, f"{i:06d}"), range(200000, 200020)))
    print("parallel codes", {c: codes.count(c) for c in set(codes)})
    assert set(codes) <= {401, 429}
    assert _courier_login(temp_courier, "111111") == 429


# Lockout: correct PIN hidden inside a parallel burst (requests read the doc before the lock is set)
def test_correct_pin_inside_parallel_burst(temp_courier):
    pins = [f"{i:06d}" for i in range(300000, 300029)] + ["111111"]
    with ThreadPoolExecutor(30) as ex:
        codes = list(ex.map(lambda p: _courier_login(temp_courier, p), pins))
    print("burst codes", {c: codes.count(c) for c in set(codes)}, "correct ->", codes[-1])
    assert codes[-1] != 200, "correct PIN accepted although >=5 wrong guesses were sent in the same burst"


# Sequential lockout still works (5 wrong -> 429)
def test_sequential_lockout(temp_courier):
    codes = [_courier_login(temp_courier, "999999") for _ in range(5)]
    assert codes == [401] * 5
    assert _courier_login(temp_courier, "111111") == 429


# Owner reset of a business account bumps auth_version and clears lockout
def test_business_reset_revokes_old_token(owner_h, temp_biz):
    bid, email = temp_biz
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "BizPass111"}, timeout=30)
    assert r.status_code == 200, r.text
    old = {"Authorization": f"Bearer {r.json()['token']}"}
    assert requests.get(f"{API}/biz/me", headers=old, timeout=30).status_code == 200
    r = requests.put(f"{API}/businesses/{bid}/account", headers=owner_h, json={"email": email, "password": "BizPass222"}, timeout=30)
    assert r.status_code == 200
    assert requests.get(f"{API}/biz/me", headers=old, timeout=30).status_code == 401
    assert requests.post(f"{API}/auth/login", json={"email": email, "password": "BizPass111"}, timeout=30).status_code == 401
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "BizPass222"}, timeout=30)
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "business"


def test_business_reset_clears_lockout(owner_h, temp_biz):
    bid, email = temp_biz
    for _ in range(5):
        requests.post(f"{API}/auth/login", json={"email": email, "password": "wrongpass"}, timeout=30)
    assert requests.post(f"{API}/auth/login", json={"email": email, "password": "BizPass111"}, timeout=30).status_code == 429
    r = requests.put(f"{API}/businesses/{bid}/account", headers=owner_h, json={"email": email, "password": "BizPass333"}, timeout=30)
    assert r.status_code == 200
    doc = DB.users.find_one({"email": email})
    assert doc["failed_logins"] == 0 and doc["locked_until"] is None
    assert requests.post(f"{API}/auth/login", json={"email": email, "password": "BizPass333"}, timeout=30).status_code == 200


# Change password with wrong current password returns 400 with message (admin password untouched)
def test_change_password_wrong_current(owner_h):
    r = requests.post(f"{API}/auth/change-password", headers=owner_h, json={"current_password": "NotTheRight1", "new_password": "Whatever123"}, timeout=30)
    assert r.status_code == 400
    assert "actual" in r.json()["detail"]
    assert requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30).status_code == 200


# Photo token issued and usable for an order photo
def test_photo_token(owner_h):
    r = requests.get(f"{API}/photo-token", headers=owner_h, timeout=30)
    assert r.status_code == 200
    tok = r.json()["token"]
    assert isinstance(tok, str) and r.json()["expires_in"] > 0
    # photo token must not work as a session token
    assert requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=30).status_code == 401


# Regular courier logins still work
@pytest.mark.parametrize("phone,pin", [("1100000001", "123456"), ("1100000002", "654321")])
def test_courier_logins(phone, pin):
    assert _courier_login(phone, pin) == 200
