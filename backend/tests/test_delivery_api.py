# Delivery management API regression tests (auth, businesses, products, couriers, orders, courier side)
import os
import uuid
import pytest
import requests

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


# ---- Auth ----
class TestAuth:
    def test_owner_login_and_me(self, owner):
        r = requests.get(f"{BASE}/auth/me", headers=_h(owner))
        assert r.status_code == 200
        d = r.json()
        assert d["role"] == "owner" and d["email"] == "admin@delivery.com"
        assert "password_hash" not in d and "_id" not in d

    def test_bad_login(self):
        r = requests.post(f"{BASE}/auth/login", json={"email": "admin@delivery.com", "password": "wrong"})
        assert r.status_code == 401

    def test_courier_login_bad_pin(self):
        r = requests.post(f"{BASE}/auth/courier/login", json={"phone": "1100000001", "pin": "000000"})
        assert r.status_code == 401

    def test_register_and_duplicate(self):
        email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{BASE}/auth/register", json={"name": "TEST owner", "email": email, "password": "Password1"})
        assert r.status_code == 200
        tok = r.json()["token"]
        assert r.json()["user"]["role"] == "owner"
        assert requests.get(f"{BASE}/businesses", headers=_h(tok)).json() == []
        r2 = requests.post(f"{BASE}/auth/register", json={"name": "x", "email": email, "password": "Password1"})
        assert r2.status_code == 409

    def test_no_token(self):
        assert requests.get(f"{BASE}/auth/me").status_code == 401

    def test_courier_forbidden_owner_endpoints(self, courier):
        for path in ["/businesses", "/orders", "/couriers", "/dashboard"]:
            assert requests.get(f"{BASE}{path}", headers=_h(courier[0])).status_code == 403, path

    def test_owner_forbidden_courier_endpoints(self, owner):
        assert requests.get(f"{BASE}/courier/orders", headers=_h(owner)).status_code == 403


# ---- Businesses / Products ----
class TestCatalog:
    def test_business_product_crud(self, owner):
        h = _h(owner)
        lst = requests.get(f"{BASE}/businesses", headers=h).json()
        assert len(lst) >= 3 and "product_count" in lst[0]
        r = requests.post(f"{BASE}/businesses", headers=h, json={"name": "TEST_Biz", "category": "Test"})
        assert r.status_code == 200
        bid = r.json()["id"]
        assert requests.get(f"{BASE}/businesses/{bid}", headers=h).json()["name"] == "TEST_Biz"
        r = requests.put(f"{BASE}/businesses/{bid}", headers=h, json={"name": "TEST_Biz2"})
        assert r.json()["name"] == "TEST_Biz2"
        p = requests.post(f"{BASE}/products", headers=h, json={"business_id": bid, "name": "TEST_Prod", "price": 4.5})
        assert p.status_code == 200 and p.json()["price"] == 4.5
        pid = p.json()["id"]
        u = requests.put(f"{BASE}/products/{pid}", headers=h, json={"available": False})
        assert u.json()["available"] is False
        prods = requests.get(f"{BASE}/products", headers=h, params={"business_id": bid}).json()
        assert prods[0]["available"] is False
        assert requests.post(f"{BASE}/products", headers=h, json={"business_id": bid, "name": "x", "price": -1}).status_code == 422
        assert requests.delete(f"{BASE}/products/{pid}", headers=h).status_code == 200
        assert requests.delete(f"{BASE}/products/{pid}", headers=h).status_code == 404
        assert requests.delete(f"{BASE}/businesses/{bid}", headers=h).status_code == 200
        assert requests.get(f"{BASE}/businesses/{bid}", headers=h).status_code == 404


# ---- Couriers ----
class TestCouriers:
    def test_courier_crud(self, owner):
        h = _h(owner)
        cs = requests.get(f"{BASE}/couriers", headers=h).json()
        assert len(cs) >= 2 and "password_hash" not in cs[0]
        phone = "19" + uuid.uuid4().hex[:8].translate(str.maketrans("abcdef", "123456"))
        r = requests.post(f"{BASE}/couriers", headers=h, json={"name": "TEST_Cour", "phone": phone, "pin": "111111"})
        assert r.status_code == 200
        cid = r.json()["id"]
        assert requests.post(f"{BASE}/couriers", headers=h, json={"name": "dup", "phone": phone, "pin": "111111"}).status_code == 409
        assert requests.post(f"{BASE}/couriers", headers=h, json={"name": "bad", "phone": "12345678", "pin": "12"}).status_code == 422
        assert requests.post(f"{BASE}/auth/courier/login", json={"phone": phone, "pin": "111111"}).status_code == 200
        assert requests.delete(f"{BASE}/couriers/{cid}", headers=h).status_code == 200
        assert requests.delete(f"{BASE}/couriers/{cid}", headers=h).status_code == 404


# ---- Orders ----
class TestOrders:
    def test_order_flow(self, owner, courier):
        h = _h(owner)
        biz = requests.get(f"{BASE}/businesses", headers=h).json()[0]
        prods = requests.get(f"{BASE}/products", headers=h, params={"business_id": biz["id"]}).json()
        p1, p2 = prods[0], prods[1]
        body = {"business_id": biz["id"], "customer_name": "TEST_Cust", "address": "Calle 1",
                "items": [{"product_id": p1["id"], "qty": 2}, {"product_id": p2["id"], "qty": 1}], "delivery_fee": 1.5}
        r = requests.post(f"{BASE}/orders", headers=h, json=body)
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["total"] == round(p1["price"] * 2 + p2["price"] + 1.5, 2)
        assert o["status"] == "nuevo" and o["number"] > 1000
        oid = o["id"]
        d = requests.get(f"{BASE}/orders/{oid}", headers=h).json()
        assert d["customer_name"] == "TEST_Cust" and d["courier"] is None
        assert any(x["id"] == oid for x in requests.get(f"{BASE}/orders", headers=h, params={"status": "nuevo"}).json())
        assert all(x["status"] == "en_camino" for x in requests.get(f"{BASE}/orders", headers=h, params={"status": "en_camino"}).json())
        r = requests.patch(f"{BASE}/orders/{oid}/status", headers=h, json={"status": "preparacion"})
        assert r.json()["status"] == "preparacion" and len(r.json()["history"]) == 2
        assert requests.patch(f"{BASE}/orders/{oid}/status", headers=h, json={"status": "bogus"}).status_code == 422
        r = requests.patch(f"{BASE}/orders/{oid}/assign", headers=h, json={"courier_id": courier[1]})
        assert r.json()["courier_name"] == "Carlos Gómez" and r.json()["courier"]["id"] == courier[1]
        # courier side
        ch = _h(courier[0])
        co = requests.get(f"{BASE}/courier/orders", headers=ch).json()
        assert any(x["id"] == oid for x in co["active"])
        assert requests.patch(f"{BASE}/courier/orders/{oid}/status", headers=ch, json={"status": "cancelado"}).status_code == 400
        assert requests.patch(f"{BASE}/courier/orders/{oid}/status", headers=ch, json={"status": "en_camino"}).json()["status"] == "en_camino"
        assert requests.patch(f"{BASE}/courier/orders/{oid}/status", headers=ch, json={"status": "entregado"}).json()["status"] == "entregado"
        co = requests.get(f"{BASE}/courier/orders", headers=ch).json()
        assert any(x["id"] == oid for x in co["delivered"])
        # closed orders cannot be reassigned
        r = requests.patch(f"{BASE}/orders/{oid}/assign", headers=h, json={"courier_id": None})
        assert r.status_code == 400

    def test_order_validation(self, owner):
        h = _h(owner)
        biz = requests.get(f"{BASE}/businesses", headers=h).json()
        assert requests.post(f"{BASE}/orders", headers=h, json={"business_id": biz[0]["id"], "customer_name": "TEST_x", "address": "y", "items": []}).status_code == 200
        other = requests.get(f"{BASE}/products", headers=h, params={"business_id": biz[1]["id"]}).json()[0]
        r = requests.post(f"{BASE}/orders", headers=h, json={"business_id": biz[0]["id"], "customer_name": "x", "address": "y", "items": [{"product_id": other["id"], "qty": 1}]})
        assert r.status_code == 400
        assert requests.get(f"{BASE}/orders/badid", headers=h).status_code == 404

    def test_dashboard(self, owner):
        d = requests.get(f"{BASE}/dashboard", headers=_h(owner)).json()
        for k in ["revenue_today", "orders_today", "delivered_today", "counts", "couriers_total", "couriers_online", "recent"]:
            assert k in d
        assert d["couriers_total"] >= 2 and isinstance(d["recent"], list)


# ---- Courier location ----
class TestCourierLocation:
    def test_location_and_online(self, owner, courier):
        ch = _h(courier[0])
        assert requests.post(f"{BASE}/courier/location", headers=ch, json={"lat": 40.4168, "lng": -3.7038}).status_code == 200
        c = [x for x in requests.get(f"{BASE}/couriers", headers=_h(owner)).json() if x["id"] == courier[1]][0]
        assert c["lat"] == 40.4168 and c["online"] is True
        r = requests.post(f"{BASE}/courier/online", headers=ch, json={"online": False})
        assert r.json()["online"] is False
        c = [x for x in requests.get(f"{BASE}/couriers", headers=_h(owner)).json() if x["id"] == courier[1]][0]
        assert c["online"] is False
        requests.post(f"{BASE}/courier/online", headers=ch, json={"online": True})
