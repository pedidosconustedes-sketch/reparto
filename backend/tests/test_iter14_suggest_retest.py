# Iteration 14 retest: OSM autocomplete Nominatim fallback, postcode label dedupe, latency
import os
import time
import requests
import pytest

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = BASE_URL + "/api"


@pytest.fixture(scope="module")
def owner():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"owner login failed {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


def suggest(h, q):
    time.sleep(1.2)  # respect Nominatim 1 req/s
    t = time.time()
    r = requests.get(f"{API}/places/autocomplete", headers=h, params={"q": q}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    d["_elapsed"] = time.time() - t
    print(q, "->", round(d["_elapsed"], 2), "s", [s["description"] for s in d["suggestions"]])
    return d


# Postcode-only label must not repeat the postcode
class TestPostcodeLabel:
    def test_label_no_duplicate(self, owner):
        d = suggest(owner, "28013")
        descs = [s["description"] for s in d["suggestions"]]
        assert descs
        assert descs[0].startswith("28013"), descs
        assert all(x.count("28013") <= 1 for x in descs), descs

    def test_other_postcode(self, owner):
        d = suggest(owner, "08001")
        descs = [s["description"] for s in d["suggestions"]]
        assert descs and all(x.count("08001") <= 1 for x in descs), descs


# Street + postcode: fallback returns results, 28013 first, each has coords
class TestFallback:
    def test_street_postcode(self, owner):
        d = suggest(owner, "Calle Mayor 28013")
        s = d["suggestions"]
        assert s and "28013" in s[0]["description"]
        assert s[0]["description"].startswith("Calle Mayor")
        # iter15: CartoCiudad street-only rows (callejero) may have no coords (lat None)
        assert all(x["lat"] is None or isinstance(x["lat"], float) for x in s)
        # Street-only results (no house number) are marked approximate on purpose.
        assert all(x["exact"] is False for x in s if x["description"].startswith("Calle Mayor,"))  # iter15: POI rows with a number may be exact

    def test_street_city(self, owner):
        d = suggest(owner, "Calle Mayor Madrid")
        assert 0 < len(d["suggestions"]) <= 8

    def test_with_house_number_still_works(self, owner):
        d = suggest(owner, "Calle Mayor 5 28013")
        assert d["suggestions"] and "28013" in d["suggestions"][0]["description"]

    def test_cached_fast(self, owner):
        # Second call of same query should be cached and Photon skipped -> fast
        d = suggest(owner, "Calle Mayor 28013")
        assert d["_elapsed"] < 4, d["_elapsed"]

    def test_short_query_and_auth(self, owner):
        r = requests.get(f"{API}/places/autocomplete", params={"q": "Calle Mayor"}, timeout=30)
        assert r.status_code in (401, 403)
