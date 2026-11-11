# Iteration 15: payment defaults to 'pagado' when amount=0 (owner + business) and CartoCiudad autocomplete
import os
import time
import uuid

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = BASE_URL + "/api"
ADDR = "Calle Alcala 50, Madrid (28014)"


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    yield db
    db.orders.delete_many({"customer_name": {"$regex": "^TEST_iter15"}})
    c.close()


@pytest.fixture(scope="module")
def owner():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"owner login failed {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def biz_id(owner):
    r = requests.get(f"{API}/businesses", headers=owner, timeout=30)
    assert r.status_code == 200 and r.json(), r.text
    return r.json()[0]["id"]


@pytest.fixture(scope="module")
def biz_login(owner, mongo):
    # Temporary business + login account (deleted afterwards)
    bid = requests.post(f"{API}/businesses", headers=owner, json={"name": "TEST_iter15Biz", "address": "Calle Mayor 1, Madrid", "phone": "1100000097"}, timeout=60).json()["id"]
    email = f"test_iter15_{uuid.uuid4().hex[:6]}@delivery.com"
    r = requests.put(f"{API}/businesses/{bid}/account", headers=owner, json={"email": email, "password": "Iter15Pass1"}, timeout=30)
    assert r.status_code == 200, r.text
    lr = requests.post(f"{API}/auth/login", json={"email": email, "password": "Iter15Pass1"}, timeout=30)
    assert lr.status_code == 200, lr.text
    yield {"Authorization": f"Bearer {lr.json()['token']}"}
    requests.delete(f"{API}/businesses/{bid}", headers=owner, timeout=30)
    assert mongo.users.count_documents({"email": email}) == 0


def order_body(bid, amount, pm, name):
    return {"business_id": bid, "customer_name": name, "address": ADDR, "dest_lat": 40.4194, "dest_lng": -3.6916,
            "amount": amount, "delivery_fee": 2, "payment_method": pm}


# Owner order payment default
class TestOwnerPayment:
    def test_zero_amount_forces_pagado(self, owner, biz_id, mongo):
        r = requests.post(f"{API}/orders", headers=owner, json=order_body(biz_id, 0, "efectivo", "TEST_iter15_o0"), timeout=30)
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["payment_method"] == "pagado"
        g = requests.get(f"{API}/orders/{o['id']}", headers=owner, timeout=30).json()
        assert g["payment_method"] == "pagado"
        assert abs(g["dest_lat"] - 40.4194) < 1e-6 and abs(g["dest_lng"] + 3.6916) < 1e-6

    @pytest.mark.parametrize("pm", ["efectivo", "datafono", "pagado"])
    def test_amount_keeps_method(self, owner, biz_id, pm):
        r = requests.post(f"{API}/orders", headers=owner, json=order_body(biz_id, 12.5, pm, f"TEST_iter15_o_{pm}"), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["payment_method"] == pm
        assert r.json()["amount"] == 12.5

    def test_default_method_with_amount_is_efectivo(self, owner, biz_id):
        b = order_body(biz_id, 5, "efectivo", "TEST_iter15_o_def")
        b.pop("payment_method")
        r = requests.post(f"{API}/orders", headers=owner, json=b, timeout=30)
        assert r.status_code == 200 and r.json()["payment_method"] == "efectivo"


# Business order payment default
class TestBizPayment:
    def test_biz_zero_amount_pagado(self, biz_login):
        r = requests.post(f"{API}/biz/orders", headers=biz_login, json=order_body("x", 0, "datafono", "TEST_iter15_b0"), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["payment_method"] == "pagado"
        g = requests.get(f"{API}/biz/orders/{r.json()['id']}", headers=biz_login, timeout=30)
        assert g.status_code == 200 and g.json()["payment_method"] == "pagado"

    def test_biz_amount_keeps_method(self, biz_login):
        r = requests.post(f"{API}/biz/orders", headers=biz_login, json=order_body("x", 9, "datafono", "TEST_iter15_b9"), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["payment_method"] == "datafono"


def suggest(h, q, **kw):
    time.sleep(0.5)  # be gentle with CartoCiudad
    r = requests.get(f"{API}/places/autocomplete", headers=h, params={"q": q, **kw}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    print(q, "->", [(s["description"], s.get("exact")) for s in d["suggestions"]])
    return d


CASES = [
    ("alcala 50", "Calle Alcala 50, Madrid (28014)"),
    ("Calle Mayor 5", "Calle Mayor 5, Madrid (28012)"),
    ("gran via 28", "Calle Gran Via 28, Madrid (28013)"),
    ("calle del pez 12", "Calle Pez 12, Madrid (28004)"),
    ("Avenida de America 10", "Avenida America 10, Madrid (28028)"),
]


# CartoCiudad autocomplete
class TestCartoCiudad:
    @pytest.mark.parametrize("q,first", CASES)
    def test_main_cases(self, owner, q, first):
        d = suggest(owner, q)
        s0 = d["suggestions"][0]
        assert s0["description"] == first
        assert s0["exact"] is True
        assert isinstance(s0["lat"], float) and isinstance(s0["lng"], float)
        assert 40.3 < s0["lat"] < 40.6 and -3.9 < s0["lng"] < -3.5

    @pytest.mark.parametrize("q,num", [("Calle de Alcala 350", "350"), ("Paseo de la Castellana 200", "200"),
                                       ("Calle de Bravo Murillo 300", "300"), ("Calle de Toledo 120", "120"),
                                       ("Calle de Arturo Soria 250", "250")])
    def test_high_numbers(self, owner, q, num):
        d = suggest(owner, q)
        s0 = d["suggestions"][0]
        assert f" {num}," in s0["description"] and "Madrid" in s0["description"], s0
        assert s0["exact"] is True and s0["lat"] and s0["lng"]

    def test_postcode_filter(self, owner):
        d = suggest(owner, "Calle Mayor 5 28012")
        s0 = d["suggestions"][0]
        assert s0["description"] == "Calle Mayor 5, Madrid (28012)" and s0["exact"] is True

    def test_alcala_50_coords(self, owner):
        s0 = suggest(owner, "Calle de Alcala 50")["suggestions"][0]
        assert s0["description"] == ADDR
        assert abs(s0["lat"] - 40.4194) < 0.003 and abs(s0["lng"] + 3.6916) < 0.003

    def test_with_near(self, owner):
        d = suggest(owner, "Calle Mayor 5", lat=40.4168, lng=-3.7038)
        assert d["suggestions"][0]["description"] == "Calle Mayor 5, Madrid (28012)"

    def test_street_only_not_exact(self, owner):
        d = suggest(owner, "Calle de Serrano")
        assert d["suggestions"]
        for s in d["suggestions"]:
            if not any(ch.isdigit() for ch in s["description"].split("(")[0]):
                assert s["exact"] is False, s
