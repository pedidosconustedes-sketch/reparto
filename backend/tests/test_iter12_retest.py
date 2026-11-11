import re
# Iteration 12 retest: OSM address ranking (Photon + Nominatim fallback), business_photo on courier
# endpoints, business-side new order (no fee), business autocomplete. Cleans up everything it creates.
import io
import os
import base64
import time

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
MADRID = {"lat": 40.4168, "lng": -3.7038}


def login(body, path="/auth/login"):
    r = requests.post(f"{API}{path}", json=body, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def owner():
    return login({"email": "admin@delivery.com", "password": "Admin12345"})


@pytest.fixture(scope="module")
def courier():
    return login({"phone": "1100000001", "pin": "123456"}, "/auth/courier/login")


def suggest(h, q, near=None):
    params = {"q": q, "session": "t12"}
    if near:
        params.update(near)
    t = time.time()
    r = requests.get(f"{API}/places/autocomplete", headers=h, params=params, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    print(f"\n[{q}] near={bool(near)} {time.time() - t:.1f}s source={d.get('source')}")
    for s in d["suggestions"]:
        print("   ", s["description"], s.get("lat"), s.get("lng"))
    return d


# ---- Address ranking (OSM path) ----
class TestAddressRanking:
    def test_gran_via_28_first(self, owner):
        d = suggest(owner, "Gran Via 28 Madrid")
        assert d["source"] == "osm"
        first = d["suggestions"][0]["description"]
        assert re.search(r"Gran V[ií]a 28\b", first) and "28013" in first and "Madrid" in first, first

    def test_gran_via_28_near_madrid(self, owner):
        d = suggest(owner, "Gran Via 28 Madrid", MADRID)
        assert re.search(r"Gran V[ií]a 28\b", d["suggestions"][0]["description"])  # iter15: CartoCiudad labels have no accents

    def test_alcala_50_is_madrid_street(self, owner):
        time.sleep(1.1)
        d = suggest(owner, "Calle de Alcala 50 Madrid")
        first = d["suggestions"][0]
        assert re.search(r"Alcal[aá] 50\b", first["description"]) and "Henares" not in first["description"], first
        assert "Madrid" in first["description"], first
        assert 40.38 < first["lat"] < 40.48 and -3.75 < first["lng"] < -3.6, first  # inside Madrid city

    def test_calle_mayor_5(self, owner):
        time.sleep(1.1)
        d = suggest(owner, "Calle Mayor 5 Madrid")
        first = d["suggestions"][0]
        assert "Mayor" in first["description"] and "Madrid" in first["description"], first
        assert 40.38 < first["lat"] < 40.48, first

    def test_fuencarral_45(self, owner):
        time.sleep(1.1)
        d = suggest(owner, "Calle de Fuencarral 45 Madrid")
        first = d["suggestions"][0]
        assert "Fuencarral" in first["description"] and "Madrid" in first["description"], first
        assert 40.38 < first["lat"] < 40.48, first

    def test_suggestions_have_coords_and_unique(self, owner):
        d = suggest(owner, "Gran Via 28 Madrid")
        descs = [s["description"].casefold() for s in d["suggestions"]]
        assert len(descs) == len(set(descs))
        assert all(isinstance(s.get("lat"), float) and isinstance(s.get("lng"), float) for s in d["suggestions"])
        assert all("_num" not in s for s in d["suggestions"])

    def test_short_and_unauth(self, owner):
        assert requests.get(f"{API}/places/autocomplete", headers=owner, params={"q": "ab"}, timeout=30).json()["suggestions"] == []
        assert requests.get(f"{API}/places/autocomplete", params={"q": "Gran Via"}, timeout=30).status_code == 401


# ---- business_photo on courier endpoints + business new order ----
@pytest.fixture(scope="module")
def env(owner):
    cid = str(mdb.users.find_one({"phone": "1100000001", "role": "courier"})["_id"])
    r = requests.post(f"{API}/businesses", headers=owner, json={
        "name": "TEST_Biz12", "address": "Calle Mayor 5, Madrid", "phone": "1100000096",
        "default_fee": 3.5, "lat": 40.4165, "lng": -3.7058}, timeout=60)
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    r = requests.put(f"{API}/businesses/{bid}/account", headers=owner, json={"email": "test_biz12@delivery.com", "password": "BizPass1234"}, timeout=30)
    assert r.status_code == 200, r.text
    orders = []
    base = {"business_id": bid, "customer_name": "TEST_Cli12", "address": "Gran Vía 28, 28013 Madrid",
            "dest_lat": 40.4203, "dest_lng": -3.7019, "delivery_fee": 3.5, "amount": 10}
    for extra in ({"courier_id": cid}, {"open": True}):
        r = requests.post(f"{API}/orders", headers=owner, json={**base, **extra}, timeout=60)
        assert r.status_code == 200, r.text
        orders.append(r.json()["id"])
    yield {"bid": bid, "orders": orders, "cid": cid}
    requests.delete(f"{API}/businesses/{bid}/account", headers=owner, timeout=30)
    requests.delete(f"{API}/businesses/{bid}", headers=owner, timeout=30)
    mdb.orders.delete_many({"business_id": bid})
    mdb.users.delete_many({"email": "test_biz12@delivery.com"})
    mdb.businesses.delete_many({"name": "TEST_Biz12"})


class TestCourierBizPhoto:
    def test_active_has_business_photo_null(self, env, courier):
        d = requests.get(f"{API}/courier/orders", headers=courier, timeout=60).json()
        mine = [o for o in d["active"] if o["id"] == env["orders"][0]]
        assert mine and "business_photo" in mine[0] and mine[0]["business_photo"] is None

    def test_open_has_business_photo_null(self, env, courier):
        d = requests.get(f"{API}/courier/open-orders", headers=courier, timeout=60).json()
        mine = [o for o in d if o["id"] == env["orders"][1]]
        assert mine and "business_photo" in mine[0] and mine[0]["business_photo"] is None

    def test_photo_after_upload(self, env, courier):
        biz = login({"email": "test_biz12@delivery.com", "password": "BizPass1234"})
        buf = io.BytesIO()
        Image.effect_noise((64, 64), 60).convert("RGB").save(buf, "JPEG")
        r = requests.post(f"{API}/biz/photo-b64", headers=biz, json={"data": base64.b64encode(buf.getvalue()).decode()}, timeout=60)
        assert r.status_code == 200, r.text
        path = r.json()["photo"]
        act = [o for o in requests.get(f"{API}/courier/orders", headers=courier, timeout=60).json()["active"] if o["id"] == env["orders"][0]]
        opn = [o for o in requests.get(f"{API}/courier/open-orders", headers=courier, timeout=60).json() if o["id"] == env["orders"][1]]
        assert act[0]["business_photo"] == path and opn[0]["business_photo"] == path
        # Owner orders list must not leak business_photo as stored field
        assert mdb.orders.find_one({"_id": ObjectId(env["orders"][0])}).get("business_photo") is None


class TestBusinessNewOrder:
    def test_biz_order_hides_fee(self, env):
        biz = login({"email": "test_biz12@delivery.com", "password": "BizPass1234"})
        r = requests.post(f"{API}/biz/orders", headers=biz, json={
            "business_id": env["bid"], "customer_name": "TEST_Cli12b", "address": "Calle Mayor 5, 28013 Madrid",
            "dest_lat": 40.4166, "dest_lng": -3.7058, "delivery_fee": 99, "amount": 12.5, "open": True}, timeout=60)
        assert r.status_code == 200, r.text
        o = r.json()
        print("biz order keys:", sorted(o.keys()))
        assert o.get("delivery_fee") in (None, 0, 0.0) or "delivery_fee" not in o
        db = mdb.orders.find_one({"_id": ObjectId(o["id"])})
        print("stored fee:", db.get("delivery_fee"), "total:", db.get("total"))
        assert db["delivery_fee"] != 99  # client fee must be ignored

    def test_biz_autocomplete(self, env):
        biz = login({"email": "test_biz12@delivery.com", "password": "BizPass1234"})
        time.sleep(1.1)
        d = suggest(biz, "Gran Via 28 Madrid", {"lat": 40.4165, "lng": -3.7058})
        assert re.search(r"Gran V[ií]a 28\b", d["suggestions"][0]["description"])  # iter15: CartoCiudad labels have no accents
