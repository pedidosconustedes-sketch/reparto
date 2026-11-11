# Courier history (day/week/fortnight/month totals) + amount-based order creation tests
import os
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
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def courier():
    r = requests.post(f"{BASE}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"})
    assert r.status_code == 200, r.text
    d = r.json()
    return d["token"], d["user"]["id"]


@pytest.fixture(scope="module")
def courier2():
    r = requests.post(f"{BASE}/auth/courier/login", json={"phone": "1100000002", "pin": "654321"})
    assert r.status_code == 200, r.text
    d = r.json()
    return d["token"], d["user"]["id"]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    db = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
    db.orders.delete_many({"customer_name": {"$regex": "^TEST_"}})


def _hist(tok, start, end):
    return requests.get(f"{BASE}/courier/history", headers=_h(tok),
                        params={"start": start.isoformat(), "end": end.isoformat()})


def _day0(d=None):
    d = d or datetime.now(timezone.utc)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


class TestHistory:
    def test_shape_and_totals_match(self, courier):
        e = _day0() + timedelta(days=1)
        s = e - timedelta(days=45)
        r = _hist(courier[0], s, e)
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(d) >= {"orders", "count", "total_collected", "total_fees"}
        assert d["count"] == len(d["orders"]) and d["count"] > 0
        assert d["total_collected"] == round(sum(o["delivery_fee"] for o in d["orders"]), 2)  # fee-based since iter6
        assert d["total_fees"] == round(sum(o["delivery_fee"] for o in d["orders"]), 2)
        for o in d["orders"]:
            assert o["status"] == "entregado" and o["courier_id"] == courier[1]
            assert s.isoformat() <= o["updated_at"]
            assert "_id" not in o
        ts = [o["updated_at"] for o in d["orders"]]
        assert ts == sorted(ts, reverse=True)

    def test_range_partition_additive(self, courier):
        # month = sum of its two fortnights; week subset of month
        today = _day0()
        m0 = today.replace(day=1)
        m1 = (m0 + timedelta(days=32)).replace(day=1)
        q2 = m0.replace(day=16)
        full = _hist(courier[0], m0, m1).json()
        a = _hist(courier[0], m0, q2).json()
        b = _hist(courier[0], q2, m1).json()
        assert full["count"] == a["count"] + b["count"]
        assert round(a["total_collected"] + b["total_collected"], 2) == full["total_collected"]

    def test_day_range_bounds(self, courier):
        s = _day0() - timedelta(days=3)
        e = s + timedelta(days=1)
        d = _hist(courier[0], s, e).json()
        for o in d["orders"]:
            assert s.isoformat() <= o["updated_at"] < e.isoformat()

    def test_isolation_between_couriers(self, courier, courier2):
        e = _day0() + timedelta(days=1)
        s = e - timedelta(days=60)
        d1 = _hist(courier[0], s, e).json()
        d2 = _hist(courier2[0], s, e).json()
        ids1 = {o["id"] for o in d1["orders"]}
        assert not ids1 & {o["id"] for o in d2["orders"]}
        assert all(o["courier_id"] == courier2[1] for o in d2["orders"])

    def test_z_suffix_and_offset(self, courier):
        r = requests.get(f"{BASE}/courier/history", headers=_h(courier[0]),
                         params={"start": "2026-10-01T00:00:00.000Z", "end": "2026-11-01T00:00:00.000Z"})
        assert r.status_code == 200, r.text
        r2 = requests.get(f"{BASE}/courier/history", headers=_h(courier[0]),
                          params={"start": "2026-10-01T02:00:00+02:00", "end": "2026-11-01T01:00:00+01:00"})
        assert r2.status_code == 200 and r2.json()["count"] == r.json()["count"]

    def test_empty_future_range(self, courier):
        s = _day0() + timedelta(days=30)
        d = _hist(courier[0], s, s + timedelta(days=1)).json()
        assert d == {"orders": [], "count": 0, "total_collected": 0, "total_fees": 0}

    def test_invalid_dates_400(self, courier):
        r = requests.get(f"{BASE}/courier/history", headers=_h(courier[0]), params={"start": "abc", "end": "xyz"})
        assert r.status_code == 400

    def test_missing_params_422(self, courier):
        r = requests.get(f"{BASE}/courier/history", headers=_h(courier[0]))
        assert r.status_code == 422

    def test_owner_forbidden(self, owner):
        e = _day0()
        r = _hist(owner, e - timedelta(days=1), e)
        assert r.status_code == 403

    def test_no_token(self):
        r = requests.get(f"{BASE}/courier/history", params={"start": "2026-10-01", "end": "2026-10-02"})
        assert r.status_code in (401, 403)


class TestAmountOrderAndHistory:
    def test_amount_order_delivered_appears_in_history(self, owner, courier):
        h = _h(owner)
        biz = requests.get(f"{BASE}/businesses", headers=h).json()[0]
        before = _hist(courier[0], _day0(), _day0() + timedelta(days=1)).json()
        r = requests.post(f"{BASE}/orders", headers=h, json={
            "business_id": biz["id"], "customer_name": "TEST_Hist", "address": "Calle Test 1",
            "amount": 12.5, "delivery_fee": 2.25, "courier_id": courier[1]})
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["amount"] == 12.5 and o["total"] == 14.75 and o["items"] == []
        g = requests.get(f"{BASE}/orders/{o['id']}", headers=h).json()
        assert g["amount"] == 12.5 and g["total"] == 14.75
        ch = _h(courier[0])
        assert requests.patch(f"{BASE}/courier/orders/{o['id']}/status", headers=ch, json={"status": "en_camino"}).status_code == 200
        assert requests.patch(f"{BASE}/courier/orders/{o['id']}/status", headers=ch, json={"status": "entregado"}).status_code == 200
        after = _hist(courier[0], _day0(), _day0() + timedelta(days=1)).json()
        assert after["count"] == before["count"] + 1
        assert round(after["total_collected"] - before["total_collected"], 2) == 2.25  # fee-based since iter6
        assert round(after["total_fees"] - before["total_fees"], 2) == 2.25
        assert after["orders"][0]["id"] == o["id"]

    def test_negative_amount_rejected(self, owner):
        h = _h(owner)
        biz = requests.get(f"{BASE}/businesses", headers=h).json()[0]
        r = requests.post(f"{BASE}/orders", headers=h, json={
            "business_id": biz["id"], "customer_name": "TEST_Neg", "address": "x", "amount": -5})
        assert r.status_code == 422

    def test_zero_amount_no_items(self, owner):
        # Report-only: an order with amount 0 and no items is accepted
        h = _h(owner)
        biz = requests.get(f"{BASE}/businesses", headers=h).json()[0]
        r = requests.post(f"{BASE}/orders", headers=h, json={
            "business_id": biz["id"], "customer_name": "TEST_Zero", "address": "x"})
        print("zero-amount order status:", r.status_code)
