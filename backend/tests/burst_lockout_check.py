# Iteration 9: measures how many guesses in one large parallel burst are actually verified (401) before the lock (429) takes effect
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import requests
from pymongo import MongoClient

API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
o = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30).json()["token"]
H = {"Authorization": f"Bearer {o}"}
phone = "18" + str(uuid.uuid4().int)[:8]
cid = requests.post(f"{API}/couriers", headers=H, json={"name": "TEST_Burst", "phone": phone, "pin": "111111", "vehicle": "moto"}, timeout=30).json()["id"]
try:
    pins = [f"{i:06d}" for i in range(400000, 400099)] + ["111111"]
    with ThreadPoolExecutor(100) as ex:
        codes = list(ex.map(lambda p: requests.post(f"{API}/auth/courier/login", json={"phone": phone, "pin": p}, timeout=90).status_code, pins))
    print("100-request burst ->", {c: codes.count(c) for c in set(codes)}, "| correct PIN (last) ->", codes[-1])
finally:
    requests.delete(f"{API}/couriers/{cid}", headers=H, timeout=30)
    MongoClient("mongodb://localhost:27017")["test_database"].users.update_many({}, {"$set": {"failed_logins": 0, "locked_until": None}})
