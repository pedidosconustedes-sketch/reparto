# Iteration 3: geocoded pickup/dest coords, courier active orders coords, reports by_courier
import os
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient


def _base():
    url = os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip().strip('"')
    return url.rstrip("/")


BASE = _base() + "/api"


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _env(key):
    with open("/app/backend/.env") as f:
        for line in f:
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"')


@pytest.fixture(scope="module")
def owner():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"})
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def courier():
    r = requests.post(f"{BASE}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"})
    assert r.status_code == 200
    d = r.json()
    return d["token"], d["user"]["id"], d["user"]["name"]


@pytest.fixture(scope="module")
def business(owner):
    r = requests.get(f"{BASE}/businesses", headers=_h(owner))
    return r.json()[0]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    db = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
    db.orders.delete_many({"customer_name": {"$regex": "^TEST_geo"}})


def _mk(owner, bid, address, courier_id=None, amount=15.0, fee=0.0, pm="efectivo"):
    body = {"business_id": bid, "customer_name": "TEST_geo", "address": address,
            "amount": amount, "delivery_fee": fee, "payment_method": pm}
    if courier_id:
        body["courier_id"] = courier_id
    return requests.post(f"{BASE}/orders", headers=_h(owner), json=body, timeout=30)


class TestGeo:
    # Real Madrid address -> dest coords inside Madrid bbox, pickup from business
    def test_create_geocodes_real_address(self, owner, business):
        t = time.time()
        r = _mk(owner, business["id"], "Calle de Alcalá 100, Madrid")
        print("create took", round(time.time() - t, 2), "s")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["payment_method"] == "efectivo"
        assert d["pickup_address"] == business["address"]
        assert d["pickup_lat"] is not None and d["pickup_lng"] is not None
        assert d["dest_lat"] is not None, "Madrid address not geocoded"
        assert 40.3 < d["dest_lat"] < 40.6 and -3.9 < d["dest_lng"] < -3.5

    # Garbage address -> null coords, order still created
    def test_create_unknown_address_null(self, owner, business):
        r = _mk(owner, business["id"], "TEST zzqxw nowhere 99999")
        assert r.status_code == 200
        assert r.json()["dest_lat"] is None

    # Courier active orders include coords
    def test_courier_active_has_coords(self, owner, business, courier):
        oid = _mk(owner, business["id"], "Calle Gran Vía 1, Madrid", courier_id=courier[1]).json()["id"]
        r = requests.get(f"{BASE}/courier/orders", headers=_h(courier[0]))
        assert r.status_code == 200
        o = next(x for x in r.json()["active"] if x["id"] == oid)
        for k in ("pickup_address", "pickup_lat", "pickup_lng", "dest_lat", "dest_lng", "payment_method"):
            assert k in o
        assert o["pickup_lat"] is not None and o["dest_lat"] is not None


class TestByCourier:
    # by_courier sums total of non-cancelled orders per courier
    def test_by_courier_delta(self, owner, business, courier):
        now = datetime.now(timezone.utc)
        p = {"start": (now - timedelta(hours=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()}
        before = requests.get(f"{BASE}/reports", headers=_h(owner), params=p).json()
        b = next((c for c in before["by_courier"] if c["courier_id"] == courier[1]), {"count": 0, "total": 0})
        _mk(owner, business["id"], "Calle Mayor 1, Madrid", courier_id=courier[1], amount=12.5, fee=2)
        c = _mk(owner, business["id"], "Calle Mayor 1, Madrid", courier_id=courier[1], amount=50).json()["id"]
        requests.patch(f"{BASE}/orders/{c}/status", headers=_h(owner), json={"status": "cancelado"})
        after = requests.get(f"{BASE}/reports", headers=_h(owner), params=p).json()
        a = next(c for c in after["by_courier"] if c["courier_id"] == courier[1])
        assert a["name"] == courier[2]
        assert a["count"] - b["count"] == 1
        assert round(a["total"] - b["total"], 2) == 14.5
        assert round(sum(x["total"] for x in after["by_courier"]), 2) == after["revenue"]
