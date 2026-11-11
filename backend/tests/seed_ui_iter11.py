# Iteration 11: seed a delivered, unpaid owner order (pickup 27 min before delivery) for UI tests. Arg "delete <id>" removes it.
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
if len(sys.argv) > 2 and sys.argv[1] == "delete":
    print(db.orders.delete_one({"_id": ObjectId(sys.argv[2])}).deleted_count)
    sys.exit()
H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30).json()["token"]}
bid = requests.get(f"{API}/businesses", headers=H, timeout=30).json()[0]["id"]
o = requests.post(f"{API}/orders", headers=H, json={"business_id": bid, "customer_name": "TEST_Duracion", "customer_phone": "600000009",
                  "address": "Gran Vía 1, Madrid", "amount": 12, "delivery_fee": 2.5, "dest_lat": 40.42, "dest_lng": -3.70}, timeout=60).json()
for st in ("en_camino", "entregado"):
    requests.patch(f"{API}/orders/{o['id']}/status", headers=H, json={"status": st}, timeout=30)
now = datetime.now(timezone.utc)
d = db.orders.find_one({"_id": ObjectId(o["id"])})
hist = d["history"]
for h in hist:
    if h["status"] == "en_camino":
        h["at"] = (now - timedelta(minutes=27)).isoformat()
    if h["status"] == "nuevo":
        h["at"] = (now - timedelta(minutes=40)).isoformat()
db.orders.update_one({"_id": d["_id"]}, {"$set": {"history": hist}})
print(o["id"], o["number"])
