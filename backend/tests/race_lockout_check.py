# Iteration 8: checks whether parallel wrong-PIN attempts bypass the 5-attempt lockout (non-atomic counter)
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import requests

API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
o = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30).json()["token"]
H = {"Authorization": f"Bearer {o}"}
phone = "18" + str(uuid.uuid4().int)[:8]
cid = requests.post(f"{API}/couriers", headers=H, json={"name": "TEST_Race", "phone": phone, "pin": "111111", "vehicle": "moto"}, timeout=30).json()["id"]
try:
    def bad(i):
        return requests.post(f"{API}/auth/courier/login", json={"phone": phone, "pin": f"{i:06d}"}, timeout=60).status_code
    with ThreadPoolExecutor(20) as ex:
        codes = list(ex.map(bad, range(200000, 200020)))
    print("20 parallel wrong attempts ->", {c: codes.count(c) for c in set(codes)})
    print("then correct PIN ->", requests.post(f"{API}/auth/courier/login", json={"phone": phone, "pin": "111111"}, timeout=30).status_code)
finally:
    requests.delete(f"{API}/couriers/{cid}", headers=H, timeout=30)
