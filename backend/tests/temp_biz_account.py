# Iteration 9: helper to create (arg "create") or delete (arg "delete <bid>") a temporary business + login account for UI tests
import os
import sys
import requests

API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30).json()["token"]}
if sys.argv[1] == "create":
    bid = requests.post(f"{API}/businesses", headers=H, json={"name": "TEST_UIBiz", "address": "Calle Mayor 1, Madrid", "phone": "1100000098"}, timeout=60).json()["id"]
    r = requests.put(f"{API}/businesses/{bid}/account", headers=H, json={"email": "test_uibiz9@delivery.com", "password": "UiBizPass1"}, timeout=30)
    print(bid, r.status_code, r.text)
else:
    print(requests.delete(f"{API}/businesses/{sys.argv[2]}", headers=H, timeout=30).status_code)
