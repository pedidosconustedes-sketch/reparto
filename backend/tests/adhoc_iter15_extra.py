# Iteration 15 ad-hoc: accent/abbrev queries + server-side geocode via CartoCiudad when no dest coords
import os
import time
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30).json()["token"]}
for q in ["Calle de Alcalá 50", "C/ Alcala 50", "Av. de America 10", "Calle de O'Donnell 10", "Plaza Mayor 1", "calle mayor 5, madrid", "Calle Princesa 999"]:
    time.sleep(0.6)
    t = time.time()
    r = requests.get(f"{API}/places/autocomplete", headers=H, params={"q": q}, timeout=60).json()
    print(q, round(time.time() - t, 2), "s ->", [(s["description"], s["exact"]) for s in r["suggestions"][:4]])
bid = requests.get(f"{API}/businesses", headers=H, timeout=30).json()[0]["id"]
o = requests.post(f"{API}/orders", headers=H, json={"business_id": bid, "customer_name": "TEST_iter15_geo", "address": "Calle de Alcala 50, Madrid", "amount": 0}, timeout=60).json()
print("geocode no coords:", o.get("dest_lat"), o.get("dest_lng"), o.get("payment_method"))
c = MongoClient(os.environ["MONGO_URL"])
print("cleanup", c[os.environ["DB_NAME"]].orders.delete_many({"customer_name": {"$regex": "^TEST_iter15"}}).deleted_count)
