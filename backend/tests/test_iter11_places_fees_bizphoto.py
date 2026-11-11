# Iteration 11: address autocomplete (OSM), exact dest coords, business default_fee/lat/lng,
# business-side fee hiding, biz date filter, owner fee edit, business photo upload + access control
import io
import os
import base64
from datetime import datetime, timedelta, timezone

import pytest
import requests
from PIL import Image
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = BASE_URL + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

FORBIDDEN = {"delivery_fee", "total", "default_fee"}


def jpeg_bytes(fmt="JPEG"):
    buf = io.BytesIO()
    Image.effect_noise((128, 128), 60).convert("RGB").save(buf, fmt)
    return buf.getvalue()


def login_owner():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def login_courier(phone, pin):
    r = requests.post(f"{API}/auth/courier/login", json={"phone": phone, "pin": pin}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def owner():
    return login_owner()


@pytest.fixture(scope="module")
def biz(owner):
    """Two temp businesses with accounts; cleaned up afterwards."""
    created = []
    out = {}
    for i, fee in ((1, 3.75), (2, 2.0)):
        r = requests.post(f"{API}/businesses", headers=owner, json={
            "name": f"TEST_Biz11_{i}", "address": "Calle Mayor 5, Madrid", "phone": "1100000097",
            "default_fee": fee, "lat": 40.4165, "lng": -3.7058}, timeout=60)
        assert r.status_code == 200, r.text
        bid = r.json()["id"]
        created.append(bid)
        email = f"test_biz11_{i}@delivery.com"
        r = requests.put(f"{API}/businesses/{bid}/account", headers=owner, json={"email": email, "password": "BizPass1234"}, timeout=30)
        assert r.status_code == 200, r.text
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": "BizPass1234"}, timeout=30)
        assert r.status_code == 200, r.text
        out[i] = {"id": bid, "h": {"Authorization": "Bearer " + r.json()["token"]}, "fee": fee}
    yield out
    for bid in created:
        mdb.orders.delete_many({"business_id": bid})
        requests.delete(f"{API}/businesses/{bid}/account", headers=owner, timeout=30)
        requests.delete(f"{API}/businesses/{bid}", headers=owner, timeout=30)


def assert_no_fee(obj):
    leaked = FORBIDDEN & set(obj.keys())
    assert not leaked, f"business-side response leaks {leaked}"


# ---- Places autocomplete ----
class TestPlaces:
    def test_requires_auth(self):
        r = requests.get(f"{API}/places/autocomplete", params={"q": "Calle Mayor 5 Madrid"}, timeout=30)
        assert r.status_code == 401

    def test_osm_suggestions(self, owner):
        r = requests.get(f"{API}/places/autocomplete", headers=owner, params={"q": "Calle Mayor 5 Madrid"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] == "osm"
        assert len(d["suggestions"]) > 0
        s = d["suggestions"][0]
        assert s.get("description") and isinstance(s.get("lat"), float) and isinstance(s.get("lng"), float)
        assert s.get("source") == "osm"

    def test_short_query_empty(self, owner):
        r = requests.get(f"{API}/places/autocomplete", headers=owner, params={"q": "Ca"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["suggestions"] == []


# ---- Businesses default_fee / lat / lng ----
class TestBusinesses:
    def test_create_keeps_coords_and_fee(self, owner, biz):
        r = requests.get(f"{API}/businesses/{biz[1]['id']}", headers=owner, timeout=30)
        d = r.json()
        assert d["default_fee"] == 3.75 and d["lat"] == 40.4165 and d["lng"] == -3.7058

    def test_put_same_address_keeps_coords(self, owner, biz):
        bid = biz[2]["id"]
        r = requests.put(f"{API}/businesses/{bid}", headers=owner, json={
            "name": "TEST_Biz11_2", "address": "Calle Mayor 5, Madrid", "phone": "1100000097", "default_fee": 2.5}, timeout=60)
        assert r.status_code == 200, r.text
        d = requests.get(f"{API}/businesses/{bid}", headers=owner, timeout=30).json()
        assert d["lat"] == 40.4165 and d["lng"] == -3.7058 and d["default_fee"] == 2.5
        biz[2]["fee"] = 2.5

    def test_put_explicit_coords(self, owner, biz):
        bid = biz[2]["id"]
        r = requests.put(f"{API}/businesses/{bid}", headers=owner, json={
            "name": "TEST_Biz11_2", "address": "Calle Mayor 5, Madrid", "phone": "1100000097", "default_fee": 2.5,
            "lat": 40.5, "lng": -3.6}, timeout=60)
        assert r.status_code == 200
        assert r.json()["lat"] == 40.5 and r.json()["lng"] == -3.6


# ---- Owner orders: dest coords + fee edit ----
class TestOwnerOrders:
    def test_dest_coords_exact(self, owner, biz):
        r = requests.post(f"{API}/orders", headers=owner, json={
            "business_id": biz[1]["id"], "customer_name": "TEST_C", "customer_phone": "600000000",
            "address": "Gran Vía 1, Madrid", "amount": 10, "delivery_fee": 2,
            "dest_lat": 40.42011, "dest_lng": -3.70111}, timeout=60)
        assert r.status_code == 200, r.text
        o = requests.get(f"{API}/orders/{r.json()['id']}", headers=owner, timeout=30).json()
        assert o["dest_lat"] == 40.42011 and o["dest_lng"] == -3.70111

    def test_dest_geocoded_without_coords(self, owner, biz):
        r = requests.post(f"{API}/orders", headers=owner, json={
            "business_id": biz[1]["id"], "customer_name": "TEST_C", "customer_phone": "600000000",
            "address": "Puerta del Sol, Madrid", "amount": 10, "delivery_fee": 2}, timeout=90)
        assert r.status_code == 200, r.text
        o = requests.get(f"{API}/orders/{r.json()['id']}", headers=owner, timeout=30).json()
        assert o["dest_lat"] is not None and abs(o["dest_lat"] - 40.4) < 0.5

    def test_fee_patch_and_paid_block(self, owner, biz):
        r = requests.post(f"{API}/orders", headers=owner, json={
            "business_id": biz[1]["id"], "customer_name": "TEST_C", "customer_phone": "600000000",
            "address": "Gran Vía 1, Madrid", "amount": 10, "delivery_fee": 2, "dest_lat": 40.42, "dest_lng": -3.70}, timeout=60)
        oid_ = r.json()["id"]
        r = requests.patch(f"{API}/orders/{oid_}/fee", headers=owner, json={"delivery_fee": 4.5}, timeout=30)
        assert r.status_code == 200, r.text
        o = requests.get(f"{API}/orders/{oid_}", headers=owner, timeout=30).json()
        assert o["delivery_fee"] == 4.5 and o["total"] == 14.5
        assert requests.patch(f"{API}/orders/{oid_}/fee", headers=owner, json={"delivery_fee": -1}, timeout=30).status_code == 422
        mdb.orders.update_one({"_id": ObjectId(oid_)}, {"$set": {"courier_paid": True}})
        r = requests.patch(f"{API}/orders/{oid_}/fee", headers=owner, json={"delivery_fee": 1}, timeout=30)
        assert r.status_code == 400

    def test_fee_patch_other_role_forbidden(self, biz):
        c = login_courier("1100000001", "123456")
        r = requests.patch(f"{API}/orders/{'0' * 24}/fee", headers=c, json={"delivery_fee": 1}, timeout=30)
        assert r.status_code in (401, 403)


# ---- Business side: fee hidden, default_fee applied, date filter ----
class TestBizSide:
    def test_biz_order_uses_default_fee_and_hides_it(self, owner, biz):
        b = biz[1]
        r = requests.post(f"{API}/biz/orders", headers=b["h"], json={
            "business_id": "x", "customer_name": "TEST_BC", "customer_phone": "600000001",
            "address": "Gran Vía 1, Madrid", "amount": 20, "delivery_fee": 99, "dest_lat": 40.42, "dest_lng": -3.70}, timeout=60)
        assert r.status_code == 200, r.text
        assert_no_fee(r.json())
        oid_ = r.json()["id"]
        b["order"] = oid_
        o = requests.get(f"{API}/orders/{oid_}", headers=owner, timeout=30).json()
        assert o["delivery_fee"] == 3.75 and o["total"] == 23.75

    def test_biz_list_detail_me_hide_fee(self, biz):
        b = biz[1]
        lst = requests.get(f"{API}/biz/orders", headers=b["h"], timeout=30).json()
        assert len(lst) >= 1
        for o in lst:
            assert_no_fee(o)
        d = requests.get(f"{API}/biz/orders/{b['order']}", headers=b["h"], timeout=30).json()
        assert_no_fee(d)
        me = requests.get(f"{API}/biz/me", headers=b["h"], timeout=30).json()
        assert_no_fee(me)

    def test_biz_cancel_hides_fee(self, biz):
        b = biz[1]
        r = requests.patch(f"{API}/biz/orders/{b['order']}/cancel", headers=b["h"], timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelado"
        assert_no_fee(r.json())

    def test_biz_date_filter(self, biz):
        b = biz[1]
        # backdate one order by 40 days
        r = requests.post(f"{API}/biz/orders", headers=b["h"], json={
            "business_id": "x", "customer_name": "TEST_Old", "customer_phone": "600000002",
            "address": "Gran Vía 1, Madrid", "amount": 5, "dest_lat": 40.42, "dest_lng": -3.70}, timeout=60)
        old_id = r.json()["id"]
        old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        mdb.orders.update_one({"_id": ObjectId(old_id)}, {"$set": {"created_at": old_ts}})
        all_ids = [o["id"] for o in requests.get(f"{API}/biz/orders", headers=b["h"], timeout=30).json()]
        assert old_id in all_ids and b["order"] in all_ids
        now = datetime.now(timezone.utc)
        today = requests.get(f"{API}/biz/orders", headers=b["h"], params={
            "start": (now - timedelta(days=1)).isoformat(), "end": (now + timedelta(days=1)).isoformat()}, timeout=30).json()
        ids = [o["id"] for o in today]
        assert b["order"] in ids and old_id not in ids
        past = requests.get(f"{API}/biz/orders", headers=b["h"], params={
            "start": (now - timedelta(days=41)).isoformat(), "end": (now - timedelta(days=39)).isoformat()}, timeout=30).json()
        assert [o["id"] for o in past] == [old_id]
        bad = requests.get(f"{API}/biz/orders", headers=b["h"], params={"start": "nope", "end": "nope"}, timeout=30)
        assert bad.status_code == 400


# ---- Business photo ----
class TestBizPhoto:
    def test_reject_non_image(self, biz):
        r = requests.post(f"{API}/biz/photo", headers=biz[1]["h"], files={"file": ("x.jpg", b"A" * 500, "image/jpeg")}, timeout=30)
        assert r.status_code == 400
        r = requests.post(f"{API}/biz/photo-b64", headers=biz[1]["h"], json={"data": base64.b64encode(b"B" * 500).decode()}, timeout=30)
        assert r.status_code == 400

    def test_upload_multipart_and_b64(self, biz):
        r = requests.post(f"{API}/biz/photo", headers=biz[1]["h"], files={"file": ("p.jpg", jpeg_bytes(), "image/jpeg")}, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        png = base64.b64encode(jpeg_bytes("PNG")).decode()
        r = requests.post(f"{API}/biz/photo-b64", headers=biz[1]["h"], json={"data": "data:image/png;base64," + png}, timeout=60)
        assert r.status_code == 200, r.text

    def _get(self, bid, headers):
        tok = requests.get(f"{API}/photo-token", headers=headers, timeout=30).json()["token"]
        return requests.get(f"{API}/businesses/{bid}/photo", params={"token": tok}, timeout=30)

    def test_access_allowed(self, owner, biz):
        bid = biz[1]["id"]
        for h in (owner, biz[1]["h"], login_courier("1100000001", "123456")):
            r = self._get(bid, h)
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith("image/")

    def test_access_denied_other_business(self, biz):
        # iter15: rule changed (iter13) - any business of the same owner can see every business photo
        assert self._get(biz[1]["id"], biz[2]["h"]).status_code == 200

    def test_bad_token(self, biz):
        r = requests.get(f"{API}/businesses/{biz[1]['id']}/photo", params={"token": "garbage"}, timeout=30)
        assert r.status_code in (401, 403, 404)
