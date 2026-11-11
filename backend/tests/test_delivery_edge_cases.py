# Edge-case/business-rule checks for orders (status transitions, availability)
import requests
from test_delivery_api import BASE, _h, owner, courier  # noqa: F401


def _mk(h, cid=None, available_only=True):
    biz = requests.get(f"{BASE}/businesses", headers=h).json()[0]
    p = requests.get(f"{BASE}/products", headers=h, params={"business_id": biz["id"]}).json()[0]
    body = {"business_id": biz["id"], "customer_name": "TEST_Edge", "address": "x", "items": [{"product_id": p["id"], "qty": 1}]}
    if cid:
        body["courier_id"] = cid
    return requests.post(f"{BASE}/orders", headers=h, json=body).json(), p


def test_unavailable_product_rejected(owner):
    h = _h(owner)
    biz = requests.get(f"{BASE}/businesses", headers=h).json()[0]
    p = requests.get(f"{BASE}/products", headers=h, params={"business_id": biz["id"]}).json()[0]
    requests.put(f"{BASE}/products/{p['id']}", headers=h, json={"available": False})
    try:
        r = requests.post(f"{BASE}/orders", headers=h, json={"business_id": biz["id"], "customer_name": "TEST_Edge", "address": "x", "items": [{"product_id": p["id"], "qty": 1}]})
        if r.status_code == 200:
            requests.patch(f"{BASE}/orders/{r.json()['id']}/status", headers=h, json={"status": "cancelado"})
        assert r.status_code == 400, f"unavailable product accepted: {r.status_code}"
    finally:
        requests.put(f"{BASE}/products/{p['id']}", headers=h, json={"available": True})


def test_courier_cannot_reopen_cancelled(owner, courier):
    h = _h(owner)
    o, _ = _mk(h, courier[1])
    requests.patch(f"{BASE}/orders/{o['id']}/status", headers=h, json={"status": "cancelado"})
    r = requests.patch(f"{BASE}/courier/orders/{o['id']}/status", headers=_h(courier[0]), json={"status": "en_camino"})
    if r.status_code == 200:
        requests.patch(f"{BASE}/orders/{o['id']}/status", headers=h, json={"status": "cancelado"})
    assert r.status_code in (400, 409), f"courier re-opened cancelled order: {r.status_code}"


def test_owner_cannot_revert_delivered(owner):
    h = _h(owner)
    o, _ = _mk(h)
    requests.patch(f"{BASE}/orders/{o['id']}/status", headers=h, json={"status": "entregado"})
    r = requests.patch(f"{BASE}/orders/{o['id']}/status", headers=h, json={"status": "nuevo"})
    requests.patch(f"{BASE}/orders/{o['id']}/status", headers=h, json={"status": "cancelado"})
    assert r.status_code in (400, 409), f"delivered order reverted: {r.status_code}"
