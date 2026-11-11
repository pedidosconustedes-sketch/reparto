# Iteration 17: main admin email-collision fix (login for real account, unique index, demo admin, linked admin perms)
import os
import uuid
import subprocess
from datetime import datetime, timezone, timedelta

import jwt
import pytest
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
REAL_ID = "6ae34bf6c4b986a63025ed26"
DEMO_ID = "6ae347236362b29c3e2fb5c8"
REAL_EMAIL = "pedidosconustedes@gmail.com"
DEMO_EMAIL, DEMO_PW = "admin@delivery.com", "Admin12345"
TAG = uuid.uuid4().hex[:6]
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def real_token():
    d = db.users.find_one({"_id": ObjectId(REAL_ID)})
    return jwt.encode({"sub": REAL_ID, "role": "owner", "ver": d.get("auth_version", 0) or 0,
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
                      os.environ["JWT_SECRET"], algorithm="HS256")


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PW})
    assert r.status_code == 200, r.text
    return r.json()["token"]


# --- DB state ---
class TestDbState:
    def test_exactly_one_doc_with_real_email(self):
        docs = list(db.users.find({"email": REAL_EMAIL}))
        assert len(docs) == 1
        d = docs[0]
        assert str(d["_id"]) == REAL_ID and d["role"] == "owner" and not d.get("parent_id")
        assert (d.get("failed_logins") or 0) == 0 and d.get("locked_until") is None

    def test_demo_restored(self):
        d = db.users.find_one({"_id": ObjectId(DEMO_ID)})
        assert d["email"] == DEMO_EMAIL and d["role"] == "owner"

    def test_unique_index(self):
        idx = db.users.index_information().get("uniq_role_email")
        assert idx and idx.get("unique") is True

    def test_duplicate_insert_blocked(self):
        with pytest.raises(DuplicateKeyError):
            r = db.users.insert_one({"role": "owner", "name": "TEST_dup", "email": REAL_EMAIL, "password_hash": "x"})
            db.users.delete_one({"_id": r.inserted_id})  # cleanup if it somehow inserted
        assert db.users.count_documents({"email": REAL_EMAIL}) == 1


# --- Login against real account (ONE wrong attempt only) ---
class TestRealLogin:
    def test_one_wrong_password_401_and_counter_increments(self):
        try:
            r = requests.post(f"{API}/auth/login", json={"email": REAL_EMAIL, "password": f"TEST_wrong_{TAG}"})
            assert r.status_code == 401, r.text
            assert r.json()["detail"] == "Credenciales inválidas"
            # proves the real doc is the one checked
            assert db.users.find_one({"_id": ObjectId(REAL_ID)})["failed_logins"] == 1
        finally:
            db.users.update_one({"_id": ObjectId(REAL_ID)}, {"$set": {"failed_logins": 0, "locked_until": None}})
        assert db.users.find_one({"_id": ObjectId(REAL_ID)})["failed_logins"] == 0

    def test_nonexistent_email_401(self):
        r = requests.post(f"{API}/auth/login", json={"email": f"test_none_{TAG}@example.com", "password": "whatever1"})
        assert r.status_code == 401 and r.json()["detail"] == "Credenciales inválidas"

    def test_minted_token_me(self):
        r = requests.get(f"{API}/auth/me", headers=H(real_token()))
        assert r.status_code == 200, r.text
        me = r.json()
        assert me["id"] == REAL_ID and me["email"] == REAL_EMAIL and me["is_main"] is True

    def test_minted_token_businesses(self):
        r = requests.get(f"{API}/businesses", headers=H(real_token()))
        assert r.status_code == 200
        names = {b["name"] for b in r.json()}
        assert {"Verde", "Flores menchu"} <= names
        assert "Café Aroma" not in names


# --- Admin create duplicate ---
class TestAdminsDup:
    def test_post_admins_real_email_409(self, demo_token):
        r = requests.post(f"{API}/admins", headers=H(demo_token),
                          json={"name": "TEST dup", "email": REAL_EMAIL, "password": "Password123", "linked": True})
        assert r.status_code == 409, r.text
        assert db.users.count_documents({"email": REAL_EMAIL}) == 1

    def test_post_admins_real_email_uppercase_409(self, demo_token):
        r = requests.post(f"{API}/admins", headers=H(demo_token),
                          json={"name": "TEST dup", "email": REAL_EMAIL.upper(), "password": "Password123", "linked": True})
        assert r.status_code == 409, r.text

    def test_register_real_email_409(self):
        r = requests.post(f"{API}/auth/register", json={"name": "TEST dup", "email": REAL_EMAIL, "password": "Password123"})
        assert r.status_code in (403, 409), r.text
        assert db.users.count_documents({"email": REAL_EMAIL}) == 1


# --- Demo admin ---
class TestDemoAdmin:
    def test_demo_me(self, demo_token):
        me = requests.get(f"{API}/auth/me", headers=H(demo_token)).json()
        assert me["id"] == DEMO_ID and me["email"] == DEMO_EMAIL and me["is_main"] is True

    def test_demo_businesses(self, demo_token):
        names = {b["name"] for b in requests.get(f"{API}/businesses", headers=H(demo_token)).json()}
        assert {"Café Aroma", "Pizzería Napoli", "Farmacia Central"} <= names
        assert "Verde" not in names and "Flores menchu" not in names

    def test_courier_login(self):
        r = requests.post(f"{API}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"})
        assert r.status_code == 200, r.text


# --- Linked secondary admin cannot delete couriers ---
class TestLinkedAdmin:
    def test_linked_admin_courier_perms(self, demo_token):
        email = f"test_linked_{TAG}@example.com"
        r = requests.post(f"{API}/admins", headers=H(demo_token),
                          json={"name": "TEST Linked", "email": email, "password": "Password123", "linked": True})
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        try:
            t = requests.post(f"{API}/auth/login", json={"email": email, "password": "Password123"}).json()["token"]
            me = requests.get(f"{API}/auth/me", headers=H(t)).json()
            assert me["is_main"] is False and me.get("linked") is True
            cs = requests.get(f"{API}/couriers", headers=H(t))
            assert cs.status_code == 200 and len(cs.json()) >= 1
            cid = cs.json()[0]["id"]
            d = requests.delete(f"{API}/couriers/{cid}", headers=H(t))
            assert d.status_code == 403, d.text
        finally:
            assert requests.delete(f"{API}/admins/{aid}", headers=H(demo_token)).status_code == 200
