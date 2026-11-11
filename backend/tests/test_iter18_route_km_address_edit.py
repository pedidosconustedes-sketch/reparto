# Iteration 18: Google Routes road distance, km quote, biz km orders, amount 0 -> pagado,
# address edit (owner + business) with re-pricing, date range filter, courier accept then edit.
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
TAG = uuid.uuid4().hex[:6]
BIZ_LL = (40.4168, -3.7038)   # Puerta del Sol
DEST_LL = (40.4530, -3.6883)  # Bernabéu area (manual check: ~7.32 km)
DEST2_LL = (40.4669, -3.6889)  # Plaza de Castilla (farther)
BASE_PRICE, BASE_KM, EXTRA = 3.0, 2.0, 0.5


def H(t):
    return {"Authorization": f"Bearer {t}"}


def fee_of(km):
    return round(BASE_PRICE + max(0.0, km - BASE_KM) * EXTRA, 2)


@pytest.fixture(scope="module")
def ctx():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"})
    assert r.status_code == 200, r.text
    c = {"admin": r.json()["token"]}
    r = requests.post(f"{API}/businesses", headers=H(c["admin"]), json={
        "name": f"TEST_KmBiz_{TAG}", "address": "Puerta del Sol, Madrid", "default_fee": 4.0,
        "pricing_mode": "km", "km_base_price": BASE_PRICE, "km_base_km": BASE_KM, "km_extra_price": EXTRA,
        "lat": BIZ_LL[0], "lng": BIZ_LL[1]})
    assert r.status_code == 200, r.text
    c["bid"] = r.json()["id"]
    email = f"test_biz_{TAG}@example.com"
    r = requests.put(f"{API}/businesses/{c['bid']}/account", headers=H(c["admin"]), json={"email": email, "password": "Secret1234"})
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Secret1234"})
    assert r.status_code == 200, r.text
    c["biz"] = r.json()["token"]
    r = requests.post(f"{API}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"})
    assert r.status_code == 200, r.text
    c["courier"] = r.json()["token"]
    c["orders"] = []
    yield c
    for oid_ in c["orders"]:
        requests.patch(f"{API}/orders/{oid_}/status", headers=H(c["admin"]), json={"status": "cancelado"})
    requests.delete(f"{API}/businesses/{c['bid']}/account", headers=H(c["admin"]))
    requests.delete(f"{API}/businesses/{c['bid']}", headers=H(c["admin"]))


class TestQuote:
    def test_quote_road_distance(self, ctx):
        r = requests.get(f"{API}/businesses/{ctx['bid']}/quote", headers=H(ctx["admin"]), params={"lat": DEST_LL[0], "lng": DEST_LL[1]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mode"] == "km"
        km = d["distance_km"]
        assert km is not None
        # straight line is ~4.2 km; road ~7.3 km
        assert 6.0 < km < 9.0, km
        assert d["fee"] == fee_of(km)
        ctx["km1"] = km

    def test_quote_requires_auth(self, ctx):
        r = requests.get(f"{API}/businesses/{ctx['bid']}/quote", params={"lat": DEST_LL[0], "lng": DEST_LL[1]})
        assert r.status_code in (401, 403)


class TestOrdersAndAddress:
    def test_biz_order_km_fee(self, ctx):
        r = requests.post(f"{API}/biz/orders", headers=H(ctx["biz"]), json={
            "business_id": "x", "customer_name": "TEST_Cliente", "address": "Estadio Bernabéu, Madrid",
            "amount": 20, "payment_method": "efectivo", "dest_lat": DEST_LL[0], "dest_lng": DEST_LL[1]})
        assert r.status_code == 200, r.text
        o = r.json()
        ctx["orders"].append(o["id"])
        ctx["biz_oid"] = o["id"]
        assert o["distance_km"] is not None and 6.0 < o["distance_km"] < 9.0
        assert o["delivery_fee"] == fee_of(o["distance_km"])
        assert o["total"] == round(20 + o["delivery_fee"], 2)
        assert o["payment_method"] == "efectivo"
        assert "dest_lat" not in o and "courier_paid" not in o

    def test_owner_order_amount_zero_pagado(self, ctx):
        r = requests.post(f"{API}/orders", headers=H(ctx["admin"]), json={
            "business_id": ctx["bid"], "customer_name": "TEST_Zero", "address": "Estadio Bernabéu, Madrid",
            "amount": 0, "delivery_fee": 5, "payment_method": "efectivo", "dest_lat": DEST_LL[0], "dest_lng": DEST_LL[1]})
        assert r.status_code == 200, r.text
        o = r.json()
        ctx["orders"].append(o["id"])
        ctx["owner_oid"] = o["id"]
        assert o["payment_method"] == "pagado"
        assert o["delivery_fee"] == 5  # owner sets fee
        assert o["distance_km"] is not None

    def test_biz_order_amount_zero_pagado(self, ctx):
        r = requests.post(f"{API}/biz/orders", headers=H(ctx["biz"]), json={
            "business_id": "x", "customer_name": "TEST_Zero2", "address": "Bernabéu", "payment_method": "datafono",
            "dest_lat": DEST_LL[0], "dest_lng": DEST_LL[1]})
        assert r.status_code == 200, r.text
        ctx["orders"].append(r.json()["id"])
        assert r.json()["payment_method"] == "pagado"

    def test_owner_change_address_reprices(self, ctx):
        r = requests.patch(f"{API}/orders/{ctx['owner_oid']}/address", headers=H(ctx["admin"]), json={
            "address": "Plaza de Castilla, Madrid", "lat": DEST2_LL[0], "lng": DEST2_LL[1]})
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["address"] == "Plaza de Castilla, Madrid"
        assert o["dest_lat"] == DEST2_LL[0]
        assert o["distance_km"] is not None and o["distance_km"] > 0
        assert o["delivery_fee"] == fee_of(o["distance_km"])
        assert o["total"] == round(o["amount"] + o["delivery_fee"], 2)
        g = requests.get(f"{API}/orders/{ctx['owner_oid']}", headers=H(ctx["admin"])).json()
        assert g["address"] == "Plaza de Castilla, Madrid" and g["delivery_fee"] == o["delivery_fee"]

    def test_courier_accept_then_biz_change_address(self, ctx):
        r = requests.post(f"{API}/courier/orders/{ctx['biz_oid']}/accept", headers=H(ctx["courier"]))
        assert r.status_code == 200, r.text
        old_km = r.json()["distance_km"]
        r = requests.patch(f"{API}/biz/orders/{ctx['biz_oid']}/address", headers=H(ctx["biz"]), json={
            "address": "Plaza de Castilla, Madrid", "lat": DEST2_LL[0], "lng": DEST2_LL[1]})
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["address"] == "Plaza de Castilla, Madrid"
        assert o["distance_km"] != old_km
        assert o["delivery_fee"] == fee_of(o["distance_km"])
        assert o["total"] == round(20 + o["delivery_fee"], 2)
        assert "dest_lat" not in o
        g = requests.get(f"{API}/biz/orders/{ctx['biz_oid']}", headers=H(ctx["biz"])).json()
        assert g["delivery_fee"] == o["delivery_fee"] and g["courier_id"]

    def test_change_address_geocode_without_coords(self, ctx):
        r = requests.patch(f"{API}/orders/{ctx['owner_oid']}/address", headers=H(ctx["admin"]), json={"address": "Estadio Santiago Bernabéu, Madrid"})
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["dest_lat"] is not None
        assert o["delivery_fee"] == fee_of(o["distance_km"])

    def test_change_address_validation(self, ctx):
        r = requests.patch(f"{API}/orders/{ctx['owner_oid']}/address", headers=H(ctx["admin"]), json={"address": "ab"})
        assert r.status_code == 422

    def test_biz_cannot_edit_other_business_order(self, ctx):
        r = requests.get(f"{API}/orders", headers=H(ctx["admin"]))
        other = next((o for o in r.json() if o["business_id"] != ctx["bid"]), None)
        if not other:
            pytest.skip("no other orders")
        r = requests.patch(f"{API}/biz/orders/{other['id']}/address", headers=H(ctx["biz"]), json={"address": "Calle Falsa 123"})
        assert r.status_code == 404

    def test_closed_order_rejected(self, ctx):
        oid_ = ctx["owner_oid"]
        assert requests.patch(f"{API}/orders/{oid_}/status", headers=H(ctx["admin"]), json={"status": "cancelado"}).status_code == 200
        r = requests.patch(f"{API}/orders/{oid_}/address", headers=H(ctx["admin"]), json={"address": "Calle Mayor 1, Madrid"})
        assert r.status_code == 400
        r = requests.patch(f"{API}/biz/orders/{oid_}/address", headers=H(ctx["biz"]), json={"address": "Calle Mayor 1, Madrid"})
        assert r.status_code == 400

    def test_delivered_order_rejected(self, ctx):
        oid_ = ctx["biz_oid"]
        for st in ("en_camino", "entregado"):
            r = requests.patch(f"{API}/orders/{oid_}/status", headers=H(ctx["admin"]), json={"status": st})
            assert r.status_code == 200, r.text
        r = requests.patch(f"{API}/biz/orders/{oid_}/address", headers=H(ctx["biz"]), json={"address": "Calle Mayor 1, Madrid"})
        assert r.status_code == 400

    def test_date_range_filter(self, ctx):
        now = datetime.now(timezone.utc)
        s, e = (now - timedelta(hours=1)).isoformat(), (now + timedelta(hours=1)).isoformat()
        r = requests.get(f"{API}/orders", headers=H(ctx["admin"]), params={"start": s, "end": e})
        assert r.status_code == 200
        ids = {o["id"] for o in r.json()}
        assert set(ctx["orders"]) <= ids
        r = requests.get(f"{API}/orders", headers=H(ctx["admin"]), params={"start": (now - timedelta(days=400)).isoformat(), "end": (now - timedelta(days=399)).isoformat()})
        assert r.status_code == 200 and not (set(ctx["orders"]) & {o["id"] for o in r.json()})
        r = requests.get(f"{API}/orders", headers=H(ctx["admin"]), params={"start": "bad", "end": "bad"})
        assert r.status_code == 400
