# Iteration 20: courier incidents visible on order lists (owner /orders?active, /dashboard recent, /biz/orders) + notify links
import os
import re
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
TAG = uuid.uuid4().hex[:6]


def H(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def ctx():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"})
    assert r.status_code == 200, r.text
    m = r.json()["token"]
    r = requests.post(f"{API}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"})
    assert r.status_code == 200, r.text
    ct, cid = r.json()["token"], r.json()["user"]["id"]
    r = requests.post(f"{API}/businesses", headers=H(m), json={"name": f"TEST_IncBiz_{TAG}", "address": "Calle Mayor 1, Madrid", "default_fee": 4})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    em = f"tinc{TAG}@example.com"
    assert requests.put(f"{API}/businesses/{bid}/account", headers=H(m), json={"email": em, "password": "Secret1234"}).status_code == 200
    bt = requests.post(f"{API}/auth/login", json={"email": em, "password": "Secret1234"}).json()["token"]
    r = requests.post(f"{API}/orders", headers=H(m), json={"business_id": bid, "customer_name": f"TEST_Inc_{TAG}", "address": "Calle Alcalá 10, Madrid",
                                                          "amount": 20, "delivery_fee": 4, "courier_id": cid}, timeout=30)
    assert r.status_code == 200, r.text
    c = {"m": m, "ct": ct, "cid": cid, "bid": bid, "bt": bt, "order": r.json()}
    yield c
    requests.patch(f"{API}/orders/{c['order']['id']}/status", headers=H(m), json={"status": "cancelado"})
    requests.delete(f"{API}/businesses/{bid}/account", headers=H(m))
    requests.delete(f"{API}/businesses/{bid}", headers=H(m))


# Incident endpoint contract
def test_incident_returns_ok_and_incident(ctx):
    oid = ctx["order"]["id"]
    r = requests.post(f"{API}/courier/orders/{oid}/incident", headers=H(ctx["ct"]), json={"type": "cliente_no_responde", "note": "  TEST no contesta  "})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    inc = d["incident"]
    assert inc["type"] == "cliente_no_responde" and inc["label"] == "El cliente no responde"
    assert inc["note"] == "TEST no contesta" and inc["by"] and inc["at"]


def test_second_incident_and_validation(ctx):
    oid = ctx["order"]["id"]
    r = requests.post(f"{API}/courier/orders/{oid}/incident", headers=H(ctx["ct"]), json={"type": "direccion_incorrecta", "note": "TEST portal 3B"})
    assert r.status_code == 200 and r.json()["incident"]["label"] == "Dirección incorrecta"
    assert requests.post(f"{API}/courier/orders/{oid}/incident", headers=H(ctx["ct"]), json={"type": "bogus"}).status_code == 422
    assert requests.post(f"{API}/courier/orders/{oid}/incident", headers=H(ctx["ct"]), json={"type": "otro", "note": "x" * 501}).status_code == 422
    # owner/business tokens cannot report incidents
    assert requests.post(f"{API}/courier/orders/{oid}/incident", headers=H(ctx["m"]), json={"type": "otro"}).status_code in (401, 403)


# Owner list (watcher) includes incidents in order
def test_owner_active_list_has_incidents(ctx):
    oid = ctx["order"]["id"]
    lst = requests.get(f"{API}/orders", headers=H(ctx["m"]), params={"active": "true"}).json()
    o = next(x for x in lst if x["id"] == oid)
    assert [i["label"] for i in o["incidents"]] == ["El cliente no responde", "Dirección incorrecta"]
    assert o["incidents"][-1]["note"] == "TEST portal 3B"


def test_dashboard_recent_has_incidents(ctx):
    d = requests.get(f"{API}/dashboard", headers=H(ctx["m"])).json()
    o = next((x for x in d["recent"] if x["id"] == ctx["order"]["id"]), None)
    if o is None:
        pytest.skip("order not among 8 most recent active orders")
    assert len(o["incidents"]) == 2


# Business list includes incidents
def test_biz_orders_has_incidents(ctx):
    lst = requests.get(f"{API}/biz/orders", headers=H(ctx["bt"])).json()
    o = next(x for x in lst if x["id"] == ctx["order"]["id"])
    assert len(o["incidents"]) == 2 and o["incidents"][-1]["label"] == "Dirección incorrecta"
    assert "courier_paid" not in o


# Notify links in code: owner -> /order/{id}, business -> /biz-order/{id}
def test_notify_links_in_source():
    src = open("/app/backend/server.py").read()
    block = src[src.index("async def courier_incident"):src.index("# ---------------- Open tasks")]
    assert re.search(r'notify\(\[o\.owner_id\].*f"/order/\{o\.id\}"\)', block)
    assert re.search(r'notify\(biz_ids.*f"/biz-order/\{o\.id\}"\)', block)
