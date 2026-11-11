# Iteration 10: retest of atomic in-flight lockout reservation (find_one_and_update + $inc before bcrypt)
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from pymongo import MongoClient

API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
_mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB = _mc[os.environ.get("DB_NAME", "test_database")]
SEEDED = ["1100000001", "1100000002"]


@pytest.fixture(scope="module")
def owner_h():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30)
    assert r.status_code == 200, r.text
    yield {"Authorization": f"Bearer {r.json()['token']}"}
    DB.users.update_many({"$or": [{"phone": {"$in": SEEDED}}, {"email": "admin@delivery.com"}]},
                         {"$set": {"failed_logins": 0, "locked_until": None}})


@pytest.fixture
def temp_courier(owner_h):
    phone = "17" + str(uuid.uuid4().int)[:8]
    r = requests.post(f"{API}/couriers", headers=owner_h, json={"name": "TEST_Lock10", "phone": phone, "pin": "111111", "vehicle": "moto"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    cid = r.json()["id"]
    yield phone
    requests.delete(f"{API}/couriers/{cid}", headers=owner_h, timeout=30)
    DB.users.delete_many({"phone": phone})


def _login(phone, pin):
    return requests.post(f"{API}/auth/courier/login", json={"phone": phone, "pin": pin}, timeout=90).status_code


def _doc(phone):
    return DB.users.find_one({"phone": phone}) or {}


# Single correct login works and leaves counter at 0
def test_single_correct_login_resets(temp_courier):
    assert _login(temp_courier, "111111") == 200
    d = _doc(temp_courier)
    assert d.get("failed_logins", 0) == 0 and d.get("locked_until") is None


# One wrong then correct works, counter reset to 0
def test_one_wrong_then_correct(temp_courier):
    assert _login(temp_courier, "000000") == 401
    assert _doc(temp_courier).get("failed_logins") == 1
    assert _login(temp_courier, "111111") == 200
    assert _doc(temp_courier).get("failed_logins") == 0


# 4 wrong then correct still works (below threshold)
def test_four_wrong_then_correct(temp_courier):
    assert [_login(temp_courier, "000000") for _ in range(4)] == [401] * 4
    assert _login(temp_courier, "111111") == 200
    # counter reset -> 4 more wrong still allowed
    assert [_login(temp_courier, "000000") for _ in range(4)] == [401] * 4


# 100 parallel wrong -> at most 5 x 401, correct PIN then 429
def test_big_burst_max_five_checks(temp_courier):
    pins = [f"{i:06d}" for i in range(500000, 500100)]
    with ThreadPoolExecutor(100) as ex:
        codes = list(ex.map(lambda p: _login(temp_courier, p), pins))
    dist = {c: codes.count(c) for c in set(codes)}
    print("burst100", dist)
    assert set(codes) <= {401, 429}
    assert dist.get(401, 0) <= 5
    assert _login(temp_courier, "111111") == 429
    d = _doc(temp_courier)
    assert d.get("locked_until") is not None


# Correct PIN at the end of a 30-req burst must not succeed
def test_correct_pin_last_in_burst(temp_courier):
    pins = [f"{i:06d}" for i in range(600000, 600029)] + ["111111"]
    with ThreadPoolExecutor(30) as ex:
        codes = list(ex.map(lambda p: _login(temp_courier, p), pins))
    print("burst30", {c: codes.count(c) for c in set(codes)}, "correct->", codes[-1])
    assert codes.count(401) <= 5
    assert codes[-1] != 200


# Lock does not extend while locked (repeated 429s keep same locked_until)
def test_lock_not_extended(temp_courier):
    for _ in range(5):
        _login(temp_courier, "000000")
    lu1 = _doc(temp_courier).get("locked_until")
    assert lu1 is not None
    time.sleep(1.2)
    assert _login(temp_courier, "000000") == 429
    assert _doc(temp_courier).get("locked_until") == lu1


# Expired lock -> login works again
def test_expired_lock_allows_login(temp_courier):
    for _ in range(5):
        _login(temp_courier, "000000")
    assert _login(temp_courier, "111111") == 429
    from datetime import datetime, timedelta, timezone
    DB.users.update_one({"phone": temp_courier}, {"$set": {"locked_until": datetime.now(timezone.utc) - timedelta(seconds=5)}})
    assert _login(temp_courier, "111111") == 200
    assert _doc(temp_courier).get("failed_logins") == 0


# Unknown phone -> 401 (no doc created)
def test_unknown_phone_401():
    assert _login("1999999999", "123456") == 401


# Regression: owner + seeded courier logins
def test_owner_login():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30)
    assert r.status_code == 200 and r.json()["user"]["role"] == "owner"


@pytest.mark.parametrize("phone,pin", [("1100000001", "123456"), ("1100000002", "654321")])
def test_seeded_courier_login(phone, pin):
    r = requests.post(f"{API}/auth/courier/login", json={"phone": phone, "pin": pin}, timeout=30)
    assert r.status_code == 200 and r.json()["user"]["role"] == "courier"
