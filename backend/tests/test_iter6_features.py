# Iteration 6: assigned_at, scheduled_for, pickup_phone, settings emergency phones, courier/orders sections, payouts sum
import time
from datetime import datetime, timezone

import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient

from test_reports_payment_photo import BASE, _h, _env

CARLOS = {"phone": "1100000001", "pin": "123456"}
LUCIA = {"phone": "1100000002", "pin": "654321"}


@pytest.fixture(scope="module")
def db():
    return MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


@pytest.fixture(scope="module")
def owner():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _courier(creds):
    r = requests.post(f"{BASE}/auth/courier/login", json=creds)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]["id"]


@pytest.fixture(scope="module")
def carlos():
    return _courier(CARLOS)


@pytest.fixture(scope="module")
def lucia():
    return _courier(LUCIA)


@pytest.fixture(scope="module")
def created(db):
    ids = []
    yield ids
    db.orders.delete_many({"_id": {"$in": [ObjectId(i) for i in ids]}, "customer_name": {"$regex": "^TEST_"}})


@pytest.fixture(scope="module")
def biz(owner):
    bs = requests.get(f"{BASE}/businesses", headers=_h(owner)).json()
    assert bs
    return bs[0]


def _new(owner, biz, created, courier_id=None, fee=2.0, **extra):
    body = {"business_id": biz["id"], "customer_name": "TEST_iter6", "customer_phone": "600000000",
            "address": "Calle de Alcalá 100, Madrid", "items": [], "amount": 10.0, "delivery_fee": fee,
            "payment_method": "efectivo", "courier_id": courier_id, **extra}
    r = requests.post(f"{BASE}/orders", headers=_h(owner), json=body)
    assert r.status_code in (200, 201), r.text
    o = r.json()
    created.append(o["id"])
    return o


# --- Order creation: assigned_at / scheduled_for / pickup_phone
class TestOrderCreate:
    def test_create_with_courier_sets_assigned_at(self, owner, biz, carlos, created):
        o = _new(owner, biz, created, courier_id=carlos[1])
        assert o["assigned_at"]
        dt = datetime.fromisoformat(o["assigned_at"])
        assert abs((datetime.now(timezone.utc) - dt).total_seconds()) < 120
        assert o["pickup_phone"] == (biz.get("phone") or "")

    def test_create_without_courier_no_assigned_at(self, owner, biz, created):
        o = _new(owner, biz, created)
        assert o["assigned_at"] is None

    def test_scheduled_for_stored(self, owner, biz, created):
        sf = "2030-05-10T14:30:00+02:00"
        o = _new(owner, biz, created, scheduled_for=sf)
        g = requests.get(f"{BASE}/orders/{o['id']}", headers=_h(owner)).json()
        assert g["scheduled_for"] == sf


# --- Assign endpoint resets assigned_at
class TestAssign:
    def test_reassign_resets_and_unassign_nulls(self, owner, biz, carlos, lucia, created):
        o = _new(owner, biz, created, courier_id=carlos[1])
        a0 = o["assigned_at"]
        time.sleep(1.2)
        r = requests.patch(f"{BASE}/orders/{o['id']}/assign", headers=_h(owner), json={"courier_id": carlos[1]})
        assert r.status_code == 200
        assert r.json()["assigned_at"] == a0, "same courier must not reset"
        r = requests.patch(f"{BASE}/orders/{o['id']}/assign", headers=_h(owner), json={"courier_id": lucia[1]})
        assert r.status_code == 200
        a1 = r.json()["assigned_at"]
        assert a1 and a1 > a0
        assert r.json()["courier_id"] == lucia[1]
        r = requests.patch(f"{BASE}/orders/{o['id']}/assign", headers=_h(owner), json={"courier_id": None})
        assert r.status_code == 200
        assert r.json()["assigned_at"] is None and r.json()["courier_id"] is None


# --- Settings emergency phones
class TestSettings:
    def test_get_put_settings(self, owner, carlos):
        orig = requests.get(f"{BASE}/settings", headers=_h(owner))
        assert orig.status_code == 200
        orig = orig.json()["emergency_phones"]
        try:
            r = requests.put(f"{BASE}/settings", headers=_h(owner), json={"emergency_phones": [" 112 ", "", "600111222"]})
            assert r.status_code == 200
            assert r.json()["emergency_phones"] == ["112", "600111222"]
            assert requests.get(f"{BASE}/settings", headers=_h(owner)).json()["emergency_phones"] == ["112", "600111222"]
            co = requests.get(f"{BASE}/courier/orders", headers=_h(carlos[0])).json()
            assert co["emergency_phones"] == ["112", "600111222"]
            r = requests.put(f"{BASE}/settings", headers=_h(owner), json={"emergency_phones": ["1"] * 6})
            assert r.status_code == 422
        finally:
            requests.put(f"{BASE}/settings", headers=_h(owner), json={"emergency_phones": orig})

    def test_settings_forbidden_for_courier(self, carlos):
        r = requests.get(f"{BASE}/settings", headers=_h(carlos[0]))
        assert r.status_code in (401, 403)


# --- Courier orders sections
class TestCourierOrders:
    def test_sections_and_since(self, owner, biz, carlos, created):
        a = _new(owner, biz, created, courier_id=carlos[1])
        d = _new(owner, biz, created, courier_id=carlos[1])
        c = _new(owner, biz, created, courier_id=carlos[1])
        assert requests.patch(f"{BASE}/orders/{d['id']}/status", headers=_h(owner), json={"status": "entregado"}).status_code == 200
        assert requests.patch(f"{BASE}/orders/{c['id']}/status", headers=_h(owner), json={"status": "cancelado"}).status_code == 200
        since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        r = requests.get(f"{BASE}/courier/orders", headers=_h(carlos[0]), params={"since": since})
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("active", "delivered", "cancelled", "emergency_phones", "pending_total", "pending_count"):
            assert k in j
        ids = lambda xs: {x["id"] for x in xs}
        assert a["id"] in ids(j["active"])
        assert d["id"] in ids(j["delivered"])
        assert c["id"] in ids(j["cancelled"])
        act = next(x for x in j["active"] if x["id"] == a["id"])
        assert act["assigned_at"] and "pickup_phone" in act
        # future since -> no delivered/cancelled
        j2 = requests.get(f"{BASE}/courier/orders", headers=_h(carlos[0]), params={"since": "2099-01-01T00:00:00+00:00"}).json()
        assert j2["delivered"] == [] and j2["cancelled"] == []

    def test_bad_since_400(self, carlos):
        r = requests.get(f"{BASE}/courier/orders", headers=_h(carlos[0]), params={"since": "garbage"})
        assert r.status_code == 400


# --- Payouts: amount equals sum of delivery_fee of marked orders
class TestPayouts:
    def test_payout_amount_equals_marked_fees(self, owner, biz, lucia, created, db):
        for fee in (1.5, 2.25, 3.0):
            o = _new(owner, biz, created, courier_id=lucia[1], fee=fee)
            assert requests.patch(f"{BASE}/orders/{o['id']}/status", headers=_h(owner), json={"status": "entregado"}).status_code == 200
        pend = next(p for p in requests.get(f"{BASE}/payouts", headers=_h(owner)).json() if p["courier_id"] == lucia[1])
        r = requests.post(f"{BASE}/payouts/{lucia[1]}", headers=_h(owner))
        assert r.status_code == 200, r.text
        j = r.json()
        marked = list(db.orders.find({"courier_id": lucia[1], "courier_paid": True, "courier_paid_at": {"$exists": True}}).sort("courier_paid_at", -1))
        ts = marked[0]["courier_paid_at"]
        this = [m for m in marked if m["courier_paid_at"] == ts]
        assert j["count"] == len(this) == pend["pending_count"]
        assert abs(j["amount"] - round(sum(m.get("delivery_fee", 0) for m in this), 2)) < 0.001
        assert abs(j["amount"] - pend["pending_total"]) < 0.001
        after = next(p for p in requests.get(f"{BASE}/payouts", headers=_h(owner)).json() if p["courier_id"] == lucia[1])
        assert after["pending_count"] == 0 and after["last_paid_amount"] == j["amount"]
        assert requests.post(f"{BASE}/payouts/{lucia[1]}", headers=_h(owner)).status_code == 400
