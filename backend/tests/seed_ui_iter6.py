# Iteration 6 UI seed: active + cancelled TEST_ orders for Carlos (run: python seed_ui_iter6.py [cleanup])
import sys
import requests
from bson import ObjectId
from pymongo import MongoClient
from test_reports_payment_photo import BASE, _h, _env

db = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
    r = db.orders.delete_many({"customer_name": {"$regex": "^TEST_"}, "owner_id": str(db.users.find_one({"email": "admin@delivery.com"})["_id"])})
    print("deleted", r.deleted_count)
    sys.exit()
tok = requests.post(f"{BASE}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}).json()["token"]
cid = requests.post(f"{BASE}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"}).json()["user"]["id"]
bs = requests.get(f"{BASE}/businesses", headers=_h(tok)).json()
print("biz phones", [(b["name"], b.get("phone")) for b in bs])
b = next((x for x in bs if x.get("phone")), bs[0])
out = []
for name in ("TEST_ui_active", "TEST_ui_cancel"):
    o = requests.post(f"{BASE}/orders", headers=_h(tok), json={
        "business_id": b["id"], "customer_name": name, "customer_phone": "600000000",
        "address": "Calle de Alcalá 100, Madrid", "amount": 10, "delivery_fee": 2.5, "courier_id": cid}).json()
    out.append(o)
requests.patch(f"{BASE}/orders/{out[1]['id']}/status", headers=_h(tok), json={"status": "cancelado"})
print("active", out[0]["number"], "pickup_phone", out[0]["pickup_phone"], "cancelled", out[1]["number"])
