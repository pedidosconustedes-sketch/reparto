# Iteration 12: seed TEST_UIBiz12 (no photo) + biz account + 1 active order for courier 1, 1 open order,
# 1 delivered order (pickup->delivery ~5s). Arg "delete" removes everything.
import os
import sys
import time

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30).json()["token"]}

if sys.argv[1] == "delete":
    for b in mdb.businesses.find({"name": "TEST_UIBiz12"}):
        bid = str(b["_id"])
        requests.delete(f"{API}/businesses/{bid}/account", headers=H, timeout=30)
        requests.delete(f"{API}/businesses/{bid}", headers=H, timeout=30)
        print("orders removed:", mdb.orders.delete_many({"business_id": bid}).deleted_count)
    mdb.users.delete_many({"email": "test_uibiz12@delivery.com"})
    mdb.businesses.delete_many({"name": "TEST_UIBiz12"})
    print("deleted")
    sys.exit()

cid = str(mdb.users.find_one({"phone": "1100000001", "role": "courier"})["_id"])
bid = requests.post(f"{API}/businesses", headers=H, json={"name": "TEST_UIBiz12", "address": "Calle Mayor 5, Madrid", "phone": "1100000095",
                                                           "default_fee": 3.5, "lat": 40.4165, "lng": -3.7058}, timeout=60).json()["id"]
print("account", requests.put(f"{API}/businesses/{bid}/account", headers=H, json={"email": "test_uibiz12@delivery.com", "password": "UiBizPass12"}, timeout=30).status_code)
base = {"business_id": bid, "customer_name": "TEST_Cli12", "address": "Gran Vía 28, 28013 Madrid", "dest_lat": 40.4202, "dest_lng": -3.702, "delivery_fee": 3.5, "amount": 10}
out = {}
for k, extra in (("active", {"courier_id": cid}), ("open", {"open": True}), ("done", {"courier_id": cid})):
    o = requests.post(f"{API}/orders", headers=H, json={**base, **extra}, timeout=60).json()
    out[k] = (o["id"], o["number"])
C = {"Authorization": "Bearer " + requests.post(f"{API}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"}, timeout=30).json()["token"]}
did = out["done"][0]
for st in ("en_camino", "entregado"):
    r = requests.patch(f"{API}/courier/orders/{did}/status", headers=C, json={"status": st, "note": ""}, timeout=30)
    print(st, r.status_code, r.text[:120])
    time.sleep(5)
print("BID", bid, out)
