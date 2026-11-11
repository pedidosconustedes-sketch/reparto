# Iteration 19: business delivery quote (/api/biz/quote) + reports custom date range.
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
DEST = (40.4530, -3.6883)  # Bernabéu
DEST2 = (40.4200, -3.6880)  # Retiro area
BIZ_EMAIL_KM = "test_iter19_km@example.com"
BIZ_EMAIL_FIX = "test_iter19_fix@example.com"
PWD = "Secret1234"


@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"})
    if r.status_code != 200:
        pytest.skip(f"admin login failed {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _make_biz(admin, name, email, **extra):
    b = requests.post(f"{API}/businesses", headers=admin, json={
        "name": name, "address": "Puerta del Sol, Madrid", "lat": 40.4168, "lng": -3.7038, **extra}).json()
    assert requests.put(f"{API}/businesses/{b['id']}/account", headers=admin, json={"email": email, "password": PWD}).status_code == 200
    t = requests.post(f"{API}/auth/login", json={"email": email, "password": PWD}).json()["token"]
    return b, {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def km_biz(admin):
    b, h = _make_biz(admin, "TEST_IT19 Km", BIZ_EMAIL_KM, default_fee=4, pricing_mode="km",
                     km_base_price=3, km_base_km=2, km_extra_price=0.5)
    yield b, h
    requests.delete(f"{API}/businesses/{b['id']}/account", headers=admin)
    requests.delete(f"{API}/businesses/{b['id']}", headers=admin)


@pytest.fixture(scope="module")
def fix_biz(admin):
    b, h = _make_biz(admin, "TEST_IT19 Fijo", BIZ_EMAIL_FIX, default_fee=3.5, pricing_mode="fixed")
    yield b, h
    requests.delete(f"{API}/businesses/{b['id']}/account", headers=admin)
    requests.delete(f"{API}/businesses/{b['id']}", headers=admin)


# --- /biz/quote: km pricing ---
class TestBizQuoteKm:
    def test_quote_km_formula(self, km_biz):
        _, h = km_biz
        r = requests.get(f"{API}/biz/quote", headers=h, params={"lat": DEST[0], "lng": DEST[1]}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(d.keys()) == {"fee", "distance_km"}
        assert isinstance(d["distance_km"], (int, float)) and 2 < d["distance_km"] < 15
        expected = round(3 + max(0, d["distance_km"] - 2) * 0.5, 2)
        assert abs(d["fee"] - expected) < 0.011

    def test_quote_matches_order_fee(self, km_biz):
        _, h = km_biz
        q = requests.get(f"{API}/biz/quote", headers=h, params={"lat": DEST2[0], "lng": DEST2[1]}, timeout=30).json()
        o = requests.post(f"{API}/biz/orders", headers=h, json={
            "business_id": "x", "customer_name": "TEST_IT19 Cliente", "address": "Retiro, Madrid", "amount": 10,
            "dest_lat": DEST2[0], "dest_lng": DEST2[1]}, timeout=30)
        assert o.status_code == 200, o.text
        od = o.json()
        print("quote", q, "order fee", od.get("delivery_fee"), od.get("distance_km"))
        assert od["delivery_fee"] == q["fee"]
        if "distance_km" in od:
            assert od["distance_km"] == q["distance_km"]
        g = requests.get(f"{API}/biz/orders/{od['id']}", headers=h).json()
        assert g["delivery_fee"] == q["fee"]

    def test_quote_requires_params(self, km_biz):
        _, h = km_biz
        assert requests.get(f"{API}/biz/quote", headers=h, params={"lat": 40.4}).status_code == 422
        assert requests.get(f"{API}/biz/quote", headers=h, params={"lat": "abc", "lng": 1}).status_code == 422

    def test_quote_auth(self, admin):
        assert requests.get(f"{API}/biz/quote", params={"lat": DEST[0], "lng": DEST[1]}).status_code in (401, 403)
        # owner token must not be accepted on business endpoint
        assert requests.get(f"{API}/biz/quote", headers=admin, params={"lat": DEST[0], "lng": DEST[1]}).status_code in (401, 403)

    def test_biz_me_hides_pricing(self, km_biz):
        _, h = km_biz
        d = requests.get(f"{API}/biz/me", headers=h).json()
        for k in ("default_fee", "km_base_price", "km_base_km", "km_extra_price", "pricing_mode"):
            assert k not in d

    def test_owner_quote_regression(self, admin, km_biz):
        b, _ = km_biz
        r = requests.get(f"{API}/businesses/{b['id']}/quote", headers=admin, params={"lat": DEST[0], "lng": DEST[1]}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["mode"] == "km" and d["distance_km"] is not None
        assert abs(d["fee"] - round(3 + max(0, d["distance_km"] - 2) * 0.5, 2)) < 0.011


# --- /biz/quote: fixed pricing ---
class TestBizQuoteFixed:
    def test_quote_fixed(self, fix_biz):
        _, h = fix_biz
        d = requests.get(f"{API}/biz/quote", headers=h, params={"lat": DEST[0], "lng": DEST[1]}).json()
        assert d == {"fee": 3.5, "distance_km": None}

    def test_fixed_order_fee(self, fix_biz):
        _, h = fix_biz
        od = requests.post(f"{API}/biz/orders", headers=h, json={
            "business_id": "x", "customer_name": "TEST_IT19 Fijo", "address": "Bernabéu, Madrid", "amount": 0,
            "dest_lat": DEST[0], "dest_lng": DEST[1], "delivery_fee": 99}).json()
        assert od["delivery_fee"] == 3.5


# --- /reports custom range ---
class TestReportsRange:
    def test_range_multi_day(self, admin):
        now = datetime.now(timezone.utc)
        s = (now - timedelta(days=40)).isoformat()
        e = (now + timedelta(days=1)).isoformat()
        r = requests.get(f"{API}/reports", headers=admin, params={"start": s, "end": e})
        assert r.status_code == 200
        d = r.json()
        for k in ("orders", "count", "delivered", "cancelled", "revenue", "by_courier"):
            assert k in d
        assert d["count"] == len(d["orders"])

    def test_range_narrow_subset(self, admin):
        now = datetime.now(timezone.utc)
        wide = requests.get(f"{API}/reports", headers=admin, params={
            "start": (now - timedelta(days=40)).isoformat(), "end": (now + timedelta(days=1)).isoformat()}).json()
        narrow = requests.get(f"{API}/reports", headers=admin, params={
            "start": (now - timedelta(days=1)).isoformat(), "end": (now + timedelta(days=1)).isoformat()}).json()
        assert narrow["count"] <= wide["count"]
        assert narrow["revenue"] <= wide["revenue"] + 0.01

    def test_range_future_empty(self, admin):
        now = datetime.now(timezone.utc)
        d = requests.get(f"{API}/reports", headers=admin, params={
            "start": (now + timedelta(days=100)).isoformat(), "end": (now + timedelta(days=101)).isoformat()}).json()
        assert d["count"] == 0 and d["orders"] == []
