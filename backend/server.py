from fastapi import FastAPI, APIRouter, Depends, HTTPException, UploadFile, File, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from bson import ObjectId
from pydantic import BaseModel, Field, EmailStr, BeforeValidator, ConfigDict
from typing import Annotated, List, Optional, Literal
from pathlib import Path
from datetime import datetime, timezone, timedelta
import os
import base64
import time
import asyncio
import uuid
import logging
import requests
import re
import threading
import bcrypt
import httpx
import jwt
from urllib.parse import quote

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_DAYS = 7
ALGO = "HS256"

app = FastAPI()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api = APIRouter(prefix="/api")
bearer = HTTPBearer(auto_error=False)

STATUSES = ["nuevo", "preparacion", "en_camino", "entregado", "cancelado"]
Status = Literal["nuevo", "preparacion", "en_camino", "entregado", "cancelado"]
PaymentMethod = Literal["pagado", "efectivo", "datafono"]
PAYMENT_METHODS = ["pagado", "efectivo", "datafono"]

# ---------------- Object storage ----------------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "reparto-delivery"
storage_key: Optional[str] = None


def init_storage() -> str:
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    global storage_key
    for attempt in range(2):
        key = init_storage()
        resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120)
        if resp.status_code == 503 and attempt == 0:
            storage_key = None
            continue
        if resp.status_code == 402:
            raise HTTPException(402, "Sin saldo de almacenamiento para subir fotos")
        resp.raise_for_status()
        return resp.json()


def get_object(path: str) -> tuple:
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


# ---------------- Geocoding (OpenStreetMap Nominatim, cached, <=1 req/s) ----------------
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_UA = "reparto-delivery/1.0 (admin@delivery.com)"
geo_lock = asyncio.Lock()
geo_last = 0.0


def _nominatim(address: str, near: Optional[tuple] = None) -> list:
    params = {"q": address, "format": "jsonv2", "limit": "1", "countrycodes": "es", "accept-language": "es"}
    if near:
        lat, lng = near
        params.update(viewbox=f"{lng - 0.6},{lat + 0.5},{lng + 0.6},{lat - 0.5}", bounded="1")
    resp = requests.get(NOMINATIM_URL, params=params, headers={"User-Agent": NOMINATIM_UA}, timeout=10)
    resp.raise_for_status()
    return resp.json()


_NOM_LOCK = threading.Lock()
_NOM_LAST = [0.0]
_NOM_CACHE: dict = {}


def _nominatim_rows(q: str, near: Optional[tuple], limit: int) -> List[dict]:
    """Nominatim fallback, cached and throttled to 1 request/second (Nominatim usage policy)."""
    ck = (q.casefold(), near and (round(near[0], 1), round(near[1], 1)))
    if ck in _NOM_CACHE:
        return _NOM_CACHE[ck]
    with _NOM_LOCK:
        wait = 1.1 - (time.time() - _NOM_LAST[0])
        if wait > 0:
            time.sleep(wait)
        _NOM_LAST[0] = time.time()
    params = {"q": q, "format": "jsonv2", "limit": str(limit), "countrycodes": "es", "accept-language": "es", "addressdetails": "1"}
    if near:
        params.update(viewbox=f"{near[1] - 0.6},{near[0] + 0.5},{near[1] + 0.6},{near[0] - 0.5}", bounded="0")
    resp = requests.get(NOMINATIM_URL, params=params, headers={"User-Agent": NOMINATIM_UA}, timeout=10)
    resp.raise_for_status()
    out = []
    for r in resp.json():
        a = r.get("address", {})
        road = a.get("road") or a.get("pedestrian") or a.get("square")
        street = " ".join(x for x in [road, a.get("house_number")] if x)
        city = a.get("city") or a.get("town") or a.get("village") or a.get("municipality")
        first = street or r.get("name")
        rest = " ".join(x for x in [a.get("postcode"), city] if x)
        if first and first in rest:
            first = None  # e.g. a postcode-only result: avoid "28013, 28013 Madrid"
        label = ", ".join(x for x in [first, rest] if x)
        out.append({"id": f"nom:{r.get('osm_type', '')}{r.get('osm_id', '')}", "description": label or r.get("display_name", ""),
                    "lat": float(r["lat"]), "lng": float(r["lon"]), "source": "osm", "_num": a.get("house_number")})
    if len(_NOM_CACHE) > 2000:
        _NOM_CACHE.clear()
    _NOM_CACHE[ck] = out
    return out


_SMALL = {"de", "del", "la", "las", "los", "el", "y", "e", "a"}


def pretty_addr(s: str) -> str:
    """'CALLE DE ALCALA 50, Madrid' -> 'Calle de Alcala 50, Madrid' (keeps apostrophes like O'Donnell)."""
    s = s.replace('"', "'")
    words = []
    for i, w in enumerate(s.split(" ")):
        lw = w.lower()
        if i > 0 and lw in _SMALL:
            words.append(lw)
        elif "'" in w:
            words.append("'".join(p[:1].upper() + p[1:].lower() for p in w.split("'")))
        else:
            words.append(w[:1].upper() + w[1:].lower() if w.isupper() else w)
    return " ".join(words)


def _cc_get(params: dict) -> List[dict]:
    resp = requests.get("https://www.cartociudad.es/geocoder/api/geocoder/candidates", params=params, headers={"User-Agent": NOMINATIM_UA}, timeout=6)
    resp.raise_for_status()
    return resp.json() or []


def cartociudad_rows(q: str, limit: int) -> List[dict]:
    """CartoCiudad (official IGN/Catastro address register): every portal number in Spain.
    Searches the province of Madrid first; postcode typed -> filtered to that postcode."""
    pc = re.search(r"\b(28\d{3})\b", q)
    clean = re.sub(r"\b(madrid|comunidad de madrid)\b", " ", q, flags=re.I)
    if pc:
        clean = clean.replace(pc.group(1), " ")
    clean = " ".join(clean.replace(",", " ").split())
    ck = ("cc", clean.casefold(), pc.group(1) if pc else None)
    if ck in _NOM_CACHE:
        return _NOM_CACHE[ck]
    params = {"q": clean or q, "limit": str(limit + 4)}
    if pc:
        params["cod_postal_filter"] = pc.group(1)
        found = _cc_get(params)
    else:
        # Madrid city first, then the rest of the Comunidad de Madrid.
        found = _cc_get({**params, "municipio_filter": "Madrid"}) + _cc_get({**params, "provincia_filter": "Madrid"})
    out = []
    seen_ids = set()
    for x in found:
        if x.get("id") in seen_ids:
            continue
        seen_ids.add(x.get("id"))
        if x.get("type") not in ("portal", "callejero", "toponimo", "Codpost"):
            continue
        addr = (x.get("address") or "").strip()
        if x.get("type") == "Codpost":
            label = f"{x.get('postalCode')} {x.get('muni') or 'Madrid'}"
        else:
            label = pretty_addr(addr)
            if x.get("postalCode") and x["postalCode"] not in label and len(x["postalCode"]) == 5:
                label += f" ({x['postalCode']})"
        lat, lng = x.get("lat"), x.get("lng")
        has_coords = bool(lat) and bool(lng)
        if x.get("type") == "Codpost" and not has_coords:
            continue
        out.append({"id": f"cc:{x.get('id')}", "description": label, "source": "osm",
                    "lat": lat if has_coords else None, "lng": lng if has_coords else None,
                    "_num": str(x["portalNumber"]) if x.get("type") == "portal" and x.get("portalNumber") else None})
        if len(out) >= limit:
            break
    if len(_NOM_CACHE) > 2000:
        _NOM_CACHE.clear()
    _NOM_CACHE[ck] = out
    return out


def osm_suggest(q: str, near: Optional[tuple], limit: int = 6) -> List[dict]:
    """CartoCiudad (all portals) first, then Photon + Nominatim; matching house number / postcode first."""
    num = re.search(r"\b(\d{1,4})\s*[a-zA-Z]?\b", q)
    want = num.group(1) if num else None
    pc = re.search(r"\b(\d{5})\b", q)
    postcode = pc.group(1) if pc else None
    rows: List[dict] = []
    try:
        rows = cartociudad_rows(q, limit)
    except Exception as ex:
        logger.warning(f"CartoCiudad suggest failed: {ex}")
    if not [r for r in rows if r.get("lat") is not None]:
        try:
            rows += _photon_rows(q, near, limit + 2) or (_photon_rows(q, None, limit + 2) if near else [])
        except Exception as ex:
            logger.warning(f"Photon suggest failed: {ex}")
    exact = [r for r in rows if want and r.get("_num") == want]
    if not rows or (want and not exact):
        try:
            nom = _nominatim_rows(q, near, 5)
            rows = nom + rows
        except Exception as ex:
            logger.warning(f"Nominatim suggest failed: {ex}")
    # Typed postcode first, then exact house number, then Madrid city.
    rows.sort(key=lambda r: (0 if postcode and postcode in r["description"] else 1,
                             0 if want and r.get("_num") == want else 1,
                             0 if re.search(r"(, |\d{5} )Madrid\b", r["description"]) else 1))
    seen, out = set(), []
    for r in rows:
        k = r["description"].casefold()
        if k in seen:
            continue
        seen.add(k)
        # Exact only when the result has a house number (matching the typed one, if any).
        r["exact"] = bool(r.get("_num")) and (not want or r.get("_num") == want)
        out.append({k2: v for k2, v in r.items() if k2 != "_num"})
        if len(out) >= limit:
            break
    return out


ABBREV = [(r"^\s*c\s*/\s*", "Calle "), (r"^\s*c\.\s*", "Calle "), (r"^\s*av(da)?\.?\s+", "Avenida "), (r"^\s*pº\.?\s*", "Paseo "), (r"^\s*pza\.?\s+", "Plaza ")]


def address_variants(address: str) -> List[str]:
    a = address
    for pat, rep in ABBREV:
        a = re.sub(pat, rep, a, flags=re.I)
    parts = [p.strip() for p in a.split(",") if p.strip()]
    out = [address, a]
    if len(parts) >= 2 and parts[1].strip().isdigit():
        street = f"{parts[0]} {parts[1]}"
        rest = parts[2:]
    else:
        street, rest = parts[0] if parts else a, parts[1:]
    city = re.sub(r"\b\d{5}\b", "", rest[-1]).strip() if rest else ""
    if city:
        out.append(f"{street}, {city}")
    out.append(street)
    # "Calle X 8 San Sebastián de los Reyes" -> split street/number from the town
    m = re.match(r"^(.*?\d+)\s+([^\d,]+)$", a.strip())
    if m:
        out.append(f"{m.group(1)}, {m.group(2)}")
    seen, res = set(), []
    for v in out:
        v = " ".join(v.split())
        if v and v.casefold() not in seen:
            seen.add(v.casefold())
            res.append(v)
    return res


async def _query(q: str, near: Optional[tuple]) -> list:
    global geo_last
    async with geo_lock:
        wait = 1.0 - (time.monotonic() - geo_last)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await run_in_threadpool(_nominatim, q, near)
        except Exception as ex:
            logger.warning(f"Geocoding failed for {q}: {ex}")
            return []
        finally:
            geo_last = time.monotonic()


def _photon(q: str, near: Optional[tuple]) -> Optional[tuple]:
    rows = _photon_rows(q, near, 5)
    return (rows[0]["lat"], rows[0]["lng"]) if rows else None


_PHOTON_DOWN_UNTIL = [0.0]


def _photon_rows(q: str, near: Optional[tuple], limit: int) -> List[dict]:
    """Photon (OpenStreetMap) results in Spain, nearest first when `near` is given."""
    if time.time() < _PHOTON_DOWN_UNTIL[0]:
        return []  # Photon recently unreachable: skip it so suggestions stay fast
    params = {"q": q, "limit": str(limit + 5), "lang": "default"}
    if near:
        params.update(lat=str(near[0]), lon=str(near[1]))
    try:
        resp = requests.get("https://photon.komoot.io/api/", params=params, headers={"User-Agent": NOMINATIM_UA}, timeout=4)
        resp.raise_for_status()
    except Exception:
        _PHOTON_DOWN_UNTIL[0] = time.time() + 300
        raise
    out = []
    for f in resp.json().get("features", []):
        p = f.get("properties", {})
        if p.get("countrycode") != "ES":
            continue
        lng, lat = f["geometry"]["coordinates"]
        if near and (abs(lat - near[0]) > 0.6 or abs(lng - near[1]) > 0.8):
            continue
        street = " ".join(x for x in [p.get("street") or (p.get("name") if p.get("type") == "street" else None), p.get("housenumber")] if x)
        main = p.get("name") if p.get("name") and p.get("type") != "street" else street
        parts = [main, street if main != street else None, " ".join(x for x in [p.get("postcode"), p.get("city") or p.get("county")] if x)]
        label = ", ".join(dict.fromkeys(x for x in parts if x))
        if label:
            out.append({"id": f"osm:{p.get('osm_type', '')}{p.get('osm_id', '')}", "description": label, "lat": lat, "lng": lng, "source": "osm", "_num": p.get("housenumber")})
        if len(out) >= limit:
            break
    return out


# ---------------- Google Maps (optional, more precise; key stays on the server) ----------------
GOOGLE_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
google_client = httpx.AsyncClient(timeout=6.0)


async def google_geocode(address: str, near: Optional[tuple]) -> Optional[tuple]:
    # Places API (New) text search: the legacy Geocoding API is not enabled on this key.
    body: dict = {"textQuery": address, "regionCode": "es", "languageCode": "es", "pageSize": 1}
    if near:
        body["locationBias"] = {"circle": {"center": {"latitude": near[0], "longitude": near[1]}, "radius": 30000.0}}
    headers = {"X-Goog-Api-Key": GOOGLE_KEY, "X-Goog-FieldMask": "places.location"}
    try:
        r = await google_client.post("https://places.googleapis.com/v1/places:searchText", json=body, headers=headers)
        res = r.json().get("places") or []
        if res and res[0].get("location"):
            loc = res[0]["location"]
            return loc["latitude"], loc["longitude"]
    except Exception as ex:
        logger.warning(f"Google geocode failed: {ex}")
    return None


async def google_autocomplete(q: str, session: str, near: Optional[tuple]) -> Optional[List[dict]]:
    body: dict = {"input": q, "includedRegionCodes": ["es"], "languageCode": "es", "sessionToken": session}
    if near:
        body["locationBias"] = {"circle": {"center": {"latitude": near[0], "longitude": near[1]}, "radius": 30000.0}}
    headers = {"X-Goog-Api-Key": GOOGLE_KEY, "X-Goog-FieldMask": "suggestions.placePrediction.placeId,suggestions.placePrediction.text"}
    try:
        r = await google_client.post("https://places.googleapis.com/v1/places:autocomplete", json=body, headers=headers)
        r.raise_for_status()
        out = []
        for s in r.json().get("suggestions", []):
            p = s.get("placePrediction")
            if p and p.get("placeId"):
                out.append({"id": p["placeId"], "description": p.get("text", {}).get("text", ""), "source": "google"})
        return out
    except Exception as ex:
        logger.warning(f"Google autocomplete failed: {ex}")
        return None


async def geocode(address: str, near: Optional[tuple] = None) -> tuple:
    address = " ".join((address or "").split())
    if len(address) < 4:
        return None, None
    key = ("g2:" if GOOGLE_KEY else "v3:") + address.casefold() + (f"@{round(near[0], 1)},{round(near[1], 1)}" if near else "")
    cached = await db.geocodes.find_one({"key": key})
    if cached:
        return cached.get("lat"), cached.get("lng")
    result = await google_geocode(address, near) if GOOGLE_KEY else None
    if not result:
        try:
            cc = await run_in_threadpool(cartociudad_rows, address, 3)
            hit = next((r for r in cc if r.get("lat") is not None and r.get("_num")), None)
            if hit:
                result = (hit["lat"], hit["lng"])
        except Exception as ex:
            logger.warning(f"CartoCiudad geocode failed: {ex}")
    if result:
        await db.geocodes.update_one({"key": key}, {"$set": {"key": key, "lat": result[0], "lng": result[1], "at": now_iso()}}, upsert=True)
        return result
    for v in address_variants(address)[:4]:
        try:
            result = await run_in_threadpool(_photon, v, near)
        except Exception as ex:
            logger.warning(f"Photon failed for {v}: {ex}")
        if not result:
            rows = await _query(v, near) if near else []
            if not rows:
                rows = await _query(v, None)
            if rows:
                result = (float(rows[0]["lat"]), float(rows[0]["lon"]))
        if result:
            lat, lng = result
            await db.geocodes.update_one({"key": key}, {"$set": {"key": key, "lat": lat, "lng": lng, "at": now_iso()}}, upsert=True)
            return lat, lng
    return None, None


async def ensure_coords(doc: dict) -> dict:
    """Fill pickup/destination coordinates once (per geocoder version) for orders missing them."""
    if doc.get("geo_v") == 2 or (doc.get("pickup_lat") is not None and doc.get("dest_lat") is not None):
        return doc
    upd: dict = {"geo_tried": True, "geo_v": 2}
    if doc.get("pickup_lat") is None:
        b = await db.businesses.find_one({"_id": ObjectId(doc["business_id"])}) if ObjectId.is_valid(doc.get("business_id", "")) else None
        if b:
            if b.get("lat") is None and b.get("address"):
                b["lat"], b["lng"] = await geocode(b["address"])
                await db.businesses.update_one({"_id": b["_id"]}, {"$set": {"lat": b["lat"], "lng": b["lng"]}})
            upd.update(pickup_address=b.get("address", ""), pickup_lat=b.get("lat"), pickup_lng=b.get("lng"))
    if doc.get("dest_lat") is None:
        plat = upd.get("pickup_lat", doc.get("pickup_lat"))
        plng = upd.get("pickup_lng", doc.get("pickup_lng"))
        upd["dest_lat"], upd["dest_lng"] = await geocode(doc.get("address", ""), (plat, plng) if plat is not None else None)
    await db.orders.update_one({"_id": doc["_id"]}, {"$set": upd})
    doc.update(upd)
    return doc


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------- Mongo base models ----------------
PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: dict):
        return cls.model_validate(doc)

    def to_mongo(self) -> dict:
        d = self.model_dump(by_alias=True, exclude={"id"})
        if self.id:
            d["_id"] = ObjectId(self.id)
        return d


class User(BaseDocument):
    role: Literal["owner", "courier", "business"]
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    password_hash: Optional[str] = None
    owner_id: Optional[str] = None
    business_id: Optional[str] = None
    profile_photo: Optional[str] = None
    auth_version: int = 0
    vehicle: Optional[str] = None
    emergency_phones: list = []  # [{name, phone}] (old: plain strings)
    parent_id: Optional[str] = None  # secondary admin -> main admin id
    linked: bool = False  # secondary admin that works on the main account's data
    online: bool = False
    lat: Optional[float] = None
    lng: Optional[float] = None
    location_at: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)

    def public(self) -> dict:
        d = self.model_dump(exclude={"password_hash"})
        d["is_main"] = self.role == "owner" and not self.parent_id
        return d


def tenant_id(doc: dict) -> Optional[str]:
    """Account whose data this user works on (linked secondary admins share the main account)."""
    if doc.get("role") == "owner":
        return doc["parent_id"] if doc.get("parent_id") and doc.get("linked") else str(doc["_id"])
    return doc.get("owner_id")


def norm_phones(items: list) -> List[dict]:
    out = []
    for p in items or []:
        if isinstance(p, str):
            p = {"name": "", "phone": p}
        phone = (p.get("phone") or "").strip()
        if phone:
            out.append({"name": (p.get("name") or "").strip()[:40], "phone": phone[:30]})
    return out[:10]


class Business(BaseDocument):
    owner_id: str
    name: str
    category: str = "General"
    address: str = ""
    phone: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    default_fee: float = 0
    pricing_mode: Literal["fixed", "km"] = "fixed"
    km_base_price: float = 0  # price that covers the first km_base_km
    km_base_km: float = 0
    km_extra_price: float = 0  # per km beyond km_base_km
    phones: list = []  # [{name, phone}]
    photo: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class Product(BaseDocument):
    owner_id: str
    business_id: str
    name: str
    price: float
    available: bool = True


class OrderItem(BaseModel):
    product_id: Optional[str] = None
    name: str
    price: float
    qty: int = 1


class StatusEvent(BaseModel):
    status: str
    at: str = Field(default_factory=now_iso)


class Order(BaseDocument):
    owner_id: str
    number: int
    business_id: str
    business_name: str
    customer_name: str
    customer_phone: str = ""
    address: str
    notes: str = ""
    items: List[OrderItem] = []
    amount: float = 0
    delivery_fee: float = 0
    total: float = 0
    status: str = "nuevo"
    courier_id: Optional[str] = None
    courier_name: Optional[str] = None
    history: List[StatusEvent] = []
    pickup_address: str = ""
    pickup_lat: Optional[float] = None
    pickup_lng: Optional[float] = None
    dest_lat: Optional[float] = None
    dest_lng: Optional[float] = None
    geo_tried: bool = False
    geo_v: int = 0
    courier_paid: bool = False
    assigned_at: Optional[str] = None
    scheduled_for: Optional[str] = None
    pickup_phone: str = ""
    payment_method: str = "efectivo"
    delivery_note: str = ""
    delivery_photo: Optional[str] = None
    business_photo: Optional[str] = None  # filled on courier endpoints only, not stored
    pickup_phones: list = []  # filled on courier endpoints only
    distance_km: Optional[float] = None
    incidents: list = []  # [{type, label, note, at, by}]
    open: bool = False
    created_by: str = "owner"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


# ---------------- Auth helpers ----------------
def hash_secret(v: str) -> str:
    return bcrypt.hashpw(v.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_secret(v: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(v.encode(), h.encode())
    except (ValueError, TypeError):
        return False


def make_token(user: User) -> str:
    payload = {"sub": user.id, "role": user.role, "ver": user.auth_version, "exp": datetime.now(timezone.utc) + timedelta(days=JWT_DAYS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGO)


def make_photo_token(user: User) -> str:
    """Short-lived, photo-only token so the session token never goes into image URLs."""
    payload = {"sub": user.id, "role": user.role, "typ": "photo", "exp": datetime.now(timezone.utc) + timedelta(minutes=PHOTO_TOKEN_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGO)


def read_photo_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGO], options={"require": ["sub", "exp"]})
    except Exception:
        raise HTTPException(401, "Enlace de foto inválido o caducado")
    if payload.get("typ") != "photo":
        raise HTTPException(401, "Enlace de foto inválido o caducado")
    return payload


# ---- Brute-force protection: lock the account after repeated failed logins ----
MAX_FAILS = 5
LOCK_MINUTES = 15
DUMMY_HASH = bcrypt.hashpw(b"never-accepted-dummy", bcrypt.gensalt()).decode()


async def check_login(doc: Optional[dict], secret: str, fail_msg: str) -> User:
    now = datetime.now(timezone.utc)
    locked_until = doc.get("locked_until") if doc else None
    if locked_until and locked_until.replace(tzinfo=timezone.utc) > now:
        mins = max(1, int((locked_until.replace(tzinfo=timezone.utc) - now).total_seconds() // 60) + 1)
        raise HTTPException(429, f"Demasiados intentos fallidos. Vuelve a intentarlo en {mins} min.")
    if not doc:
        verify_secret(secret, DUMMY_HASH)
        raise HTTPException(401, fail_msg)
    # Reserve this attempt atomically BEFORE checking the secret, so a burst of
    # parallel guesses can never get more than MAX_FAILS checks per lock window.
    d2 = await db.users.find_one_and_update(
        {"_id": doc["_id"], "$or": [{"locked_until": None}, {"locked_until": {"$exists": False}}, {"locked_until": {"$lte": now}}]},
        {"$inc": {"failed_logins": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if not d2 or d2.get("failed_logins", 0) > MAX_FAILS:
        await db.users.update_one({"_id": doc["_id"], "locked_until": {"$not": {"$gt": now}}},
                                  {"$set": {"failed_logins": 0, "locked_until": now + timedelta(minutes=LOCK_MINUTES)}})
        raise HTTPException(429, f"Demasiados intentos fallidos. Vuelve a intentarlo en {LOCK_MINUTES} min.")
    if not verify_secret(secret, doc.get("password_hash") or DUMMY_HASH):
        if d2.get("failed_logins", 0) >= MAX_FAILS:
            await db.users.update_one({"_id": doc["_id"]}, {"$set": {"failed_logins": 0, "locked_until": now + timedelta(minutes=LOCK_MINUTES)}})
        raise HTTPException(401, fail_msg)
    await db.users.update_one({"_id": doc["_id"]}, {"$set": {"failed_logins": 0, "locked_until": None}})
    return User.from_mongo(doc)


def norm_phone(p: str) -> str:
    return "".join(c for c in p if c.isdigit())


async def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> User:
    if not cred:
        raise HTTPException(401, "Autenticación requerida")
    try:
        payload = jwt.decode(cred.credentials, JWT_SECRET, algorithms=[ALGO])
        uid = ObjectId(payload["sub"])
    except Exception:
        raise HTTPException(401, "Sesión inválida o expirada")
    if payload.get("typ") == "photo":
        raise HTTPException(401, "Sesión inválida o expirada")
    doc = await db.users.find_one({"_id": uid})
    if not doc:
        raise HTTPException(401, "Usuario no existe")
    if payload.get("ver", 0) != doc.get("auth_version", 0):
        raise HTTPException(401, "Sesión inválida o expirada")
    return User.from_mongo(doc)


async def owner_user(u: User = Depends(current_user)) -> User:
    if u.role != "owner":
        raise HTTPException(403, "Solo el propietario")
    if u.parent_id and u.linked:
        # Linked secondary admin: acts on the main account's data.
        u = u.model_copy(update={"id": u.parent_id})
    return u


async def account_admin(u: User = Depends(owner_user)) -> User:
    """Can create courier/business accounts: main admin or an independent secondary admin."""
    if u.linked:
        raise HTTPException(403, "Solo el administrador principal puede crear o borrar cuentas")
    return u


async def main_admin(u: User = Depends(current_user)) -> User:
    if u.role != "owner" or u.parent_id:
        raise HTTPException(403, "Solo el administrador principal")
    return u


async def courier_user(u: User = Depends(current_user)) -> User:
    if u.role != "courier":
        raise HTTPException(403, "Solo repartidores")
    return u


async def business_user(u: User = Depends(current_user)) -> User:
    if u.role != "business" or not u.business_id:
        raise HTTPException(403, "Solo comercios")
    return u


# ---------------- Push notifications (Emergent managed relay) ----------------
PUSH_BASE_URL = "https://integrations.emergentagent.com"
PUSH_KEY = os.environ.get("EMERGENT_PUSH_KEY", "placeholder")
push_client = httpx.AsyncClient(base_url=PUSH_BASE_URL, headers={"X-Push-Key": PUSH_KEY}, timeout=10.0)


async def send_push(recipients: List[str], data: dict, idempotency_key: Optional[str] = None, _attempt: int = 0) -> None:
    recipients = [r for r in dict.fromkeys(recipients) if r]
    if not recipients:
        return
    for i in range(0, len(recipients), 100):
        payload: dict = {"recipients": recipients[i:i + 100], "data": data}
        if idempotency_key:
            payload["$idempotency_key"] = f"{idempotency_key}:{i}"
        resp = await push_client.post("/api/v1/push/trigger", json=payload)
        if resp.status_code == 401:
            raise HTTPException(500, "EMERGENT_PUSH_KEY missing or invalid")
        code = resp.json().get("code", "") if resp.headers.get("content-type", "").startswith("application/json") else ""
        if code == "idempotency_key_in_progress" and idempotency_key and _attempt < 3:
            await asyncio.sleep(3)
            return await send_push(recipients, data, idempotency_key=idempotency_key, _attempt=_attempt + 1)
        if code in ("insufficient_credits", "integration_disabled", "daily_limit_reached"):
            logger.warning(f"Push paused: {code} ({resp.status_code}): {resp.json().get('message', '')}")
            return
        resp.raise_for_status()


def notify(recipients: List[str], title: str, message: str, action_url: str = "/"):
    """Fire-and-forget push; failures never block the request."""
    async def run():
        try:
            await send_push(recipients, {"title": title, "message": message, "action_url": action_url})
        except Exception as ex:
            logger.warning(f"Push failed (non-blocking): {ex}")
    asyncio.create_task(run())


def oid(v: str) -> ObjectId:
    if not ObjectId.is_valid(v):
        raise HTTPException(404, "No encontrado")
    return ObjectId(v)


# ---------------- Schemas ----------------
class RegisterIn(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class CourierLoginIn(BaseModel):
    phone: str
    pin: str


class BusinessIn(BaseModel):
    name: str = Field(min_length=1)
    category: str = "General"
    address: str = ""
    phone: str = ""
    default_fee: float = Field(default=0, ge=0)
    pricing_mode: Literal["fixed", "km"] = "fixed"
    km_base_price: float = Field(default=0, ge=0)
    km_base_km: float = Field(default=0, ge=0)
    km_extra_price: float = Field(default=0, ge=0)
    phones: List[dict] = Field(default=[], max_length=10)
    # Exact coordinates when the address was picked from the suggestions list.
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


class FeeIn(BaseModel):
    delivery_fee: float = Field(ge=0)


class ProductIn(BaseModel):
    business_id: str
    name: str = Field(min_length=1)
    price: float = Field(ge=0)
    available: bool = True


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    available: Optional[bool] = None


class CourierIn(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=6)
    pin: str = Field(pattern=r"^\d{6}$")
    vehicle: str = "Moto"


class OrderItemIn(BaseModel):
    product_id: str
    qty: int = Field(ge=1)


class OrderIn(BaseModel):
    business_id: str
    customer_name: str = Field(min_length=1)
    customer_phone: str = ""
    address: str = Field(min_length=1)
    notes: str = ""
    items: List[OrderItemIn] = []
    amount: float = Field(default=0, ge=0)
    delivery_fee: float = Field(default=0, ge=0)
    courier_id: Optional[str] = None
    payment_method: PaymentMethod = "efectivo"
    scheduled_for: Optional[str] = None
    open: bool = False
    dest_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    dest_lng: Optional[float] = Field(default=None, ge=-180, le=180)


class PhotoB64In(BaseModel):
    data: str
    mime: str = "image/jpeg"


class BizAccountIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class SettingsIn(BaseModel):
    emergency_phones: List[dict] = Field(default=[], max_length=10)


class IncidentIn(BaseModel):
    type: Literal["cliente_no_localizable", "direccion_incorrecta", "cliente_no_responde", "pedido_no_listo", "cliente_rechaza", "otro"]
    note: str = Field(default="", max_length=500)


INCIDENT_LABEL = {"cliente_no_localizable": "Cliente no localizable", "direccion_incorrecta": "Dirección incorrecta",
                  "cliente_no_responde": "El cliente no responde", "pedido_no_listo": "El pedido no está listo",
                  "cliente_rechaza": "El cliente rechaza el pedido", "otro": "Otra incidencia"}


class StatusIn(BaseModel):
    status: Status


class CourierStatusIn(BaseModel):
    status: Status
    note: str = Field(default="", max_length=500)


class PaymentIn(BaseModel):
    payment_method: PaymentMethod


class AssignIn(BaseModel):
    courier_id: Optional[str] = None


class LocationIn(BaseModel):
    lat: float
    lng: float


class OnlineIn(BaseModel):
    online: bool


def auth_response(u: User) -> dict:
    return {"token": make_token(u), "user": u.public()}


# ---------------- Auth routes ----------------
@api.post("/auth/register")
async def register(body: RegisterIn):
    # Public sign-up is disabled: accounts are created by the administrator.
    raise HTTPException(403, "El registro está desactivado. Pide una cuenta al administrador.")


async def _register_disabled(body: RegisterIn):
    email = body.email.lower()
    if await db.users.find_one({"role": "owner", "email": email}):
        raise HTTPException(409, "Ya existe una cuenta con ese email")
    u = User(role="owner", name=body.name.strip(), email=email, password_hash=hash_secret(body.password))
    res = await db.users.insert_one(u.to_mongo())
    u.id = str(res.inserted_id)
    return auth_response(u)


@api.post("/auth/login")
async def login(body: LoginIn):
    doc = await db.users.find_one({"role": {"$in": ["owner", "business"]}, "email": body.email.lower()})
    return auth_response(await check_login(doc, body.password, "Credenciales inválidas"))


@api.post("/auth/courier/login")
async def courier_login(body: CourierLoginIn):
    doc = await db.users.find_one({"role": "courier", "phone": norm_phone(body.phone)})
    return auth_response(await check_login(doc, body.pin, "Teléfono o PIN incorrecto"))


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


@api.post("/auth/change-password")
async def change_password(body: ChangePasswordIn, u: User = Depends(current_user)):
    if u.role == "courier":
        raise HTTPException(403, "Los repartidores usan PIN; pide al administrador que lo cambie")
    if not verify_secret(body.current_password, u.password_hash or ""):
        raise HTTPException(400, "La contraseña actual no es correcta")
    if body.current_password == body.new_password:
        raise HTTPException(400, "La nueva contraseña debe ser distinta")
    await db.users.update_one({"_id": ObjectId(u.id)}, {"$set": {"password_hash": hash_secret(body.new_password)}, "$inc": {"auth_version": 1}})
    u.auth_version += 1
    # Other sessions are signed out; this device gets a fresh token.
    return auth_response(u)


@api.get("/photo-token")
async def photo_token(u: User = Depends(current_user)):
    return {"token": make_photo_token(u), "expires_in": PHOTO_TOKEN_MIN * 60}


@api.get("/auth/me")
async def me(u: User = Depends(current_user)):
    return u.public()


class PushRegisterIn(BaseModel):
    platform: str
    device_token: str


@api.post("/register-push", status_code=201)
async def register_push(body: PushRegisterIn, u: User = Depends(current_user)):
    try:
        resp = await push_client.post("/api/v1/push/users/register", json={"user_id": u.id, "platform": body.platform, "device_token": body.device_token})
    except httpx.HTTPError:
        raise HTTPException(502, "Push provider unavailable")
    if resp.status_code == 401:
        raise HTTPException(500, "EMERGENT_PUSH_KEY missing or invalid")
    if resp.status_code >= 400:
        raise HTTPException(502, "Push provider unavailable")
    return {"status": "registered"}


# ---------------- Profile photos ----------------
async def store_image(owner_id: str, data: bytes, ctype: str) -> str:
    ext = "png" if ctype == "image/png" else "jpg"
    path = f"{APP_NAME}/uploads/{owner_id}/{uuid.uuid4()}.{ext}"
    res = await run_in_threadpool(put_object, path, data, ctype)
    return res["path"]


def sniff_image(data: bytes) -> str:
    """Return the real image type from the file bytes; reject anything that isn't a photo (e.g. SVG/HTML)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis", b"hevc"):
        return "image/heic"
    raise HTTPException(400, "Solo se permiten fotos JPG, PNG, WEBP o HEIC")


def check_image(data: bytes) -> str:
    if len(data) < 200 or len(data) > MAX_PHOTO:
        raise HTTPException(400, "Foto inválida o demasiado grande")
    return sniff_image(data)


def image_response(data: bytes, cache: str) -> Response:
    try:
        ctype = sniff_image(data)
    except HTTPException:
        raise HTTPException(404, "Foto no disponible")
    return Response(content=data, media_type=ctype, headers={
        "Cache-Control": cache, "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'",
    })


@api.post("/courier/profile-photo")
async def courier_profile_photo(file: UploadFile = File(...), u: User = Depends(courier_user)):
    data = await file.read()
    ctype = check_image(data)
    path = await store_image(u.owner_id or u.id, data, ctype)
    await db.users.update_one({"_id": ObjectId(u.id)}, {"$set": {"profile_photo": path}})
    return {"ok": True, "profile_photo": path}


@api.post("/courier/profile-photo-b64")
async def courier_profile_photo_b64(body: PhotoB64In, u: User = Depends(courier_user)):
    try:
        data = base64.b64decode(body.data.split(",")[-1])
    except Exception:
        raise HTTPException(400, "Foto inválida")
    ctype = check_image(data)
    path = await store_image(u.owner_id or u.id, data, ctype)
    await db.users.update_one({"_id": ObjectId(u.id)}, {"$set": {"profile_photo": path}})
    return {"ok": True, "profile_photo": path}


@api.get("/users/{uid}/photo")
async def user_photo(uid: str, token: str):
    payload = read_photo_token(token)
    d = await db.users.find_one({"_id": oid(uid), "role": "courier"})
    if not d or not d.get("profile_photo"):
        raise HTTPException(404, "Sin foto")
    viewer = await db.users.find_one({"_id": oid(payload["sub"])})
    allowed = viewer and (
        str(viewer["_id"]) == uid
        or (viewer["role"] == "owner" and d.get("owner_id") == tenant_id(viewer))
        or (viewer["role"] == "business" and d.get("owner_id") == viewer.get("owner_id"))
    )
    if not allowed:
        raise HTTPException(404, "Sin foto")
    data, ctype = await run_in_threadpool(get_object, d["profile_photo"])
    return image_response(data, "private, max-age=300")


# ---------------- Businesses ----------------
@api.get("/businesses")
async def list_businesses(u: User = Depends(owner_user)):
    docs = await db.businesses.find({"owner_id": u.id}).sort("created_at", 1).to_list(500)
    out = []
    for d in docs:
        b = Business.from_mongo(d).model_dump()
        b["product_count"] = await db.products.count_documents({"business_id": b["id"]})
        b["active_orders"] = await db.orders.count_documents(
            {"business_id": b["id"], "status": {"$in": ["nuevo", "preparacion", "en_camino"]}}
        )
        out.append(b)
    return out


@api.post("/businesses")
async def create_business(body: BusinessIn, u: User = Depends(owner_user)):
    b = Business(owner_id=u.id, **body.model_dump())
    if body.lat is None or body.lng is None:
        b.lat, b.lng = await geocode(b.address)
    res = await db.businesses.insert_one(b.to_mongo())
    b.id = str(res.inserted_id)
    return b.model_dump()


async def get_business(bid: str, u: User) -> Business:
    d = await db.businesses.find_one({"_id": oid(bid), "owner_id": u.id})
    if not d:
        raise HTTPException(404, "Comercio no encontrado")
    return Business.from_mongo(d)


@api.get("/businesses/{bid}")
async def business_detail(bid: str, u: User = Depends(owner_user)):
    b = (await get_business(bid, u)).model_dump()
    acc = await db.users.find_one({"role": "business", "business_id": bid})
    b["account_email"] = acc.get("email") if acc else None
    return b


@api.put("/businesses/{bid}/account")
async def set_business_account(bid: str, body: BizAccountIn, u: User = Depends(account_admin)):
    b = await get_business(bid, u)
    email = body.email.lower()
    clash = await db.users.find_one({"role": {"$in": ["owner", "business"]}, "email": email})
    if clash and clash.get("business_id") != bid:
        raise HTTPException(409, "Ese email ya está en uso")
    upd = {"email": email, "password_hash": hash_secret(body.password), "name": b.name}
    acc = await db.users.find_one({"role": "business", "business_id": bid})
    if acc:
        await db.users.update_one({"_id": acc["_id"]}, {"$set": {**upd, "failed_logins": 0, "locked_until": None}, "$inc": {"auth_version": 1}})
    else:
        nu = User(role="business", owner_id=u.id, business_id=bid, **upd)
        await db.users.insert_one(nu.to_mongo())
    return {"ok": True, "account_email": email}


@api.delete("/businesses/{bid}/account")
async def delete_business_account(bid: str, u: User = Depends(account_admin)):
    await get_business(bid, u)
    await db.users.delete_many({"role": "business", "business_id": bid})
    return {"ok": True}


@api.put("/businesses/{bid}")
async def update_business(bid: str, body: BusinessIn, u: User = Depends(owner_user)):
    old = await get_business(bid, u)
    data = body.model_dump()
    if body.lat is None or body.lng is None:
        if body.address.strip() == old.address.strip() and old.lat is not None:
            data["lat"], data["lng"] = old.lat, old.lng
        else:
            data["lat"], data["lng"] = await geocode(body.address)
    await db.businesses.update_one({"_id": oid(bid)}, {"$set": data})
    return (await get_business(bid, u)).model_dump()


# ---------------- Business photo (seen by admin and couriers) ----------------
async def save_business_photo(bid: str, owner_id: str, data: bytes) -> dict:
    ctype = check_image(data)
    path = await store_image(owner_id, data, ctype)
    await db.businesses.update_one({"_id": oid(bid)}, {"$set": {"photo": path}})
    return {"ok": True, "photo": path}


@api.post("/biz/photo")
async def biz_photo_upload(file: UploadFile = File(...), u: User = Depends(business_user)):
    return await save_business_photo(u.business_id, u.owner_id, await file.read())


@api.post("/biz/photo-b64")
async def biz_photo_b64(body: PhotoB64In, u: User = Depends(business_user)):
    try:
        data = base64.b64decode(body.data.split(",")[-1])
    except Exception:
        raise HTTPException(400, "Foto inválida")
    return await save_business_photo(u.business_id, u.owner_id, data)


@api.get("/businesses/{bid}/photo")
async def business_photo(bid: str, token: str):
    payload = read_photo_token(token)
    b = await db.businesses.find_one({"_id": oid(bid)})
    viewer = await db.users.find_one({"_id": oid(payload["sub"])})
    if not b or not b.get("photo") or not viewer:
        raise HTTPException(404, "Sin foto")
    # Everyone working for the same owner (admin, couriers, any business) can see every business photo.
    viewer_owner = tenant_id(viewer)
    if viewer_owner != b["owner_id"]:
        raise HTTPException(404, "Sin foto")
    data, _ = await run_in_threadpool(get_object, b["photo"])
    return image_response(data, "private, max-age=300")


# ---------------- Address suggestions ----------------
@api.get("/places/autocomplete")
async def places_autocomplete(q: str, session: str = "", lat: Optional[float] = None, lng: Optional[float] = None, u: User = Depends(current_user)):
    q = " ".join(q.split())[:200]
    if len(q) < 3:
        return {"suggestions": [], "source": "none"}
    near = (lat, lng) if lat is not None and lng is not None else None
    if GOOGLE_KEY:
        rows = await google_autocomplete(q, session or str(uuid.uuid4()), near)
        if rows is not None:
            return {"suggestions": rows[:8], "source": "google"}
    rows = await run_in_threadpool(osm_suggest, q, near, 8)
    return {"suggestions": rows, "source": "osm"}


@api.get("/places/details")
async def places_details(place_id: str, session: str = "", u: User = Depends(current_user)):
    if not GOOGLE_KEY:
        raise HTTPException(400, "Detalles no disponibles")
    headers = {"X-Goog-Api-Key": GOOGLE_KEY, "X-Goog-FieldMask": "id,formattedAddress,location"}
    params = {"languageCode": "es", "regionCode": "es", **({"sessionToken": session} if session else {})}
    try:
        r = await google_client.get("https://places.googleapis.com/v1/places/" + quote(place_id, safe=""), headers=headers, params=params)
        r.raise_for_status()
        x = r.json()
        loc = x.get("location", {})
        return {"address": x.get("formattedAddress"), "lat": loc.get("latitude"), "lng": loc.get("longitude")}
    except Exception as ex:
        logger.warning(f"Google place details failed: {ex}")
        raise HTTPException(502, "No se pudo obtener la dirección")


@api.delete("/businesses/{bid}")
async def delete_business(bid: str, u: User = Depends(owner_user)):
    await get_business(bid, u)
    await db.businesses.delete_one({"_id": oid(bid)})
    await db.products.delete_many({"business_id": bid})
    await db.users.delete_many({"role": "business", "business_id": bid})
    return {"ok": True}


# ---------------- Products ----------------
@api.get("/products")
async def list_products(business_id: str, u: User = Depends(owner_user)):
    docs = await db.products.find({"owner_id": u.id, "business_id": business_id}).sort("name", 1).to_list(1000)
    return [Product.from_mongo(d).model_dump() for d in docs]


@api.post("/products")
async def create_product(body: ProductIn, u: User = Depends(owner_user)):
    await get_business(body.business_id, u)
    p = Product(owner_id=u.id, **body.model_dump())
    res = await db.products.insert_one(p.to_mongo())
    p.id = str(res.inserted_id)
    return p.model_dump()


@api.put("/products/{pid}")
async def update_product(pid: str, body: ProductUpdate, u: User = Depends(owner_user)):
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    res = await db.products.find_one_and_update(
        {"_id": oid(pid), "owner_id": u.id}, {"$set": upd}, return_document=True
    )
    if not res:
        raise HTTPException(404, "Producto no encontrado")
    return Product.from_mongo(res).model_dump()


@api.delete("/products/{pid}")
async def delete_product(pid: str, u: User = Depends(owner_user)):
    res = await db.products.delete_one({"_id": oid(pid), "owner_id": u.id})
    if not res.deleted_count:
        raise HTTPException(404, "Producto no encontrado")
    return {"ok": True}


# ---------------- Couriers ----------------
@api.get("/couriers")
async def list_couriers(u: User = Depends(owner_user)):
    docs = await db.users.find({"role": "courier", "owner_id": u.id}).sort("name", 1).to_list(500)
    out = []
    for d in docs:
        c = User.from_mongo(d).public()
        c["active_orders"] = await db.orders.count_documents(
            {"courier_id": c["id"], "status": {"$in": ["nuevo", "preparacion", "en_camino"]}}
        )
        out.append(c)
    return out


@api.post("/couriers")
async def create_courier(body: CourierIn, u: User = Depends(account_admin)):
    phone = norm_phone(body.phone)
    if await db.users.find_one({"role": "courier", "phone": phone}):
        raise HTTPException(409, "Ya existe un repartidor con ese teléfono")
    c = User(role="courier", name=body.name.strip(), phone=phone, password_hash=hash_secret(body.pin),
             owner_id=u.id, vehicle=body.vehicle)
    res = await db.users.insert_one(c.to_mongo())
    c.id = str(res.inserted_id)
    return c.public()


@api.delete("/couriers/{cid}")
async def delete_courier(cid: str, u: User = Depends(account_admin)):
    res = await db.users.delete_one({"_id": oid(cid), "role": "courier", "owner_id": u.id})
    if not res.deleted_count:
        raise HTTPException(404, "Repartidor no encontrado")
    await db.orders.update_many(
        {"courier_id": cid, "status": {"$in": ["nuevo", "preparacion", "en_camino"]}},
        {"$set": {"courier_id": None, "courier_name": None}},
    )
    # Business-created tasks go back to the open pool so another courier can take them.
    await db.orders.update_many(
        {"courier_id": None, "created_by": "business", "owner_id": u.id, "status": {"$in": ["nuevo", "preparacion"]}},
        {"$set": {"open": True}},
    )
    return {"ok": True}


# ---------------- Orders ----------------
async def get_courier(cid: str, owner_id: str) -> User:
    d = await db.users.find_one({"_id": oid(cid), "role": "courier", "owner_id": owner_id})
    if not d:
        raise HTTPException(404, "Repartidor no encontrado")
    return User.from_mongo(d)


@api.get("/orders")
async def list_orders(status: Optional[str] = None, business_id: Optional[str] = None, active: bool = False,
                      start: Optional[str] = None, end: Optional[str] = None, u: User = Depends(owner_user)):
    q: dict = {"owner_id": u.id}
    if status:
        q["status"] = status
    elif active:
        q["status"] = {"$in": ["nuevo", "preparacion", "en_camino"]}
    if business_id:
        q["business_id"] = business_id
    if start and end:
        s, e = parse_range(start, end)
        q["created_at"] = {"$gte": s, "$lt": e}
    docs = await db.orders.find(q).sort("created_at", -1).to_list(3000 if start else 500)
    return [Order.from_mongo(d).model_dump() for d in docs]


# ---------------- Secondary admins (main admin only) ----------------
class AdminIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    linked: bool = True


@api.get("/admins")
async def list_admins(u: User = Depends(main_admin)):
    docs = await db.users.find({"role": "owner", "parent_id": u.id}).sort("name", 1).to_list(100)
    return [User.from_mongo(d).public() for d in docs]


@api.post("/admins")
async def create_admin(body: AdminIn, u: User = Depends(main_admin)):
    email = body.email.lower()
    if await db.users.find_one({"role": {"$in": ["owner", "business"]}, "email": email}):
        raise HTTPException(409, "Ese email ya está en uso")
    a = User(role="owner", name=body.name.strip(), email=email, password_hash=hash_secret(body.password), parent_id=u.id, linked=body.linked)
    a.id = str((await db.users.insert_one(a.to_mongo())).inserted_id)
    return a.public()


@api.delete("/admins/{aid}")
async def delete_admin(aid: str, u: User = Depends(main_admin)):
    res = await db.users.delete_one({"_id": oid(aid), "role": "owner", "parent_id": u.id})
    if not res.deleted_count:
        raise HTTPException(404, "Administrador no encontrado")
    return {"ok": True}


# ---------------- Distance pricing ----------------
async def route_km(a: tuple, b: tuple) -> Optional[float]:
    """Road distance in km for driving. Google Routes API (same street routing as Google Maps navigation,
    with alternative routes; we bill the shortest) when a key is set; otherwise OSRM road routing."""
    if GOOGLE_KEY:
        # vehicleStopover snaps each point to a drivable side of the street (avoids U-turn loops);
        # we ask for the normal alternatives and an avoid-highways variant and bill the shortest real route.
        pt = lambda p: {"location": {"latLng": {"latitude": p[0], "longitude": p[1]}}, "vehicleStopover": True}
        base = {"origin": pt(a), "destination": pt(b), "travelMode": "DRIVE", "computeAlternativeRoutes": True,
                "languageCode": "es", "regionCode": "es", "units": "METRIC"}
        headers = {"X-Goog-Api-Key": GOOGLE_KEY, "X-Goog-FieldMask": "routes.distanceMeters"}

        async def call(body: dict) -> List[int]:
            try:
                r = await google_client.post("https://routes.googleapis.com/directions/v2:computeRoutes", json=body, headers=headers)
                out = [rt["distanceMeters"] for rt in r.json().get("routes", []) if rt.get("distanceMeters")]
                if not out:
                    logger.warning(f"Google Routes: no route ({r.status_code} {r.text[:200]})")
                return out
            except Exception as ex:
                logger.warning(f"Google Routes failed: {ex}")
                return []
        res = await asyncio.gather(call(base), call({**base, "routeModifiers": {"avoidHighways": True}}))
        dists = [d for lst in res for d in lst]
        if dists:
            return round(min(dists) / 1000, 2)
    try:
        r = await google_client.get(f"https://router.project-osrm.org/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}",
                                    params={"alternatives": "true", "overview": "false"})
        dists = [x["distance"] for x in r.json().get("routes", [])]
        if dists:
            return round(min(dists) / 1000, 2)
    except Exception as ex:
        logger.warning(f"OSRM route failed: {ex}")
    return None


def km_fee(b: "Business", km: float) -> float:
    return round(b.km_base_price + max(0.0, km - b.km_base_km) * b.km_extra_price, 2)


async def quote_for(b: "Business", lat: Optional[float], lng: Optional[float]) -> tuple:
    """(fee, distance_km). Fixed fee unless the business uses distance pricing and both points are known."""
    if b.pricing_mode != "km" or None in (b.lat, b.lng, lat, lng):
        return b.default_fee, None
    km = await route_km((b.lat, b.lng), (lat, lng))
    return (km_fee(b, km), km) if km is not None else (b.default_fee, None)


@api.get("/businesses/{bid}/quote")
async def business_quote(bid: str, lat: float, lng: float, u: User = Depends(owner_user)):
    b = await get_business(bid, u)
    fee, km = await quote_for(b, lat, lng)
    return {"fee": fee, "distance_km": km, "mode": b.pricing_mode}


@api.post("/orders")
async def create_order(body: OrderIn, u: User = Depends(owner_user)):
    b = await get_business(body.business_id, u)
    return await build_order(body, u.id, b, "owner")


async def build_order(body: OrderIn, owner_id: str, b: Business, created_by: str) -> dict:
    items: List[OrderItem] = []
    for it in body.items:
        pd = await db.products.find_one({"_id": oid(it.product_id), "business_id": b.id})
        if not pd:
            raise HTTPException(400, "Producto inválido")
        if not pd.get("available", True):
            raise HTTPException(400, f"{pd['name']} no está disponible")
        p = Product.from_mongo(pd)
        items.append(OrderItem(product_id=p.id, name=p.name, price=p.price, qty=it.qty))
    # Each business has its own sequence: #01, #02, … (shown to owner, business and courier).
    key = f"orders_biz_{b.id}"
    last = await db.orders.find_one({"business_id": b.id}, sort=[("number", -1)])
    await db.counters.update_one({"_id": key}, {"$max": {"seq": last["number"] if last else 0}}, upsert=True)
    counter = await db.counters.find_one_and_update({"_id": key}, {"$inc": {"seq": 1}}, return_document=ReturnDocument.AFTER)
    number = counter["seq"]
    amount = round(sum(i.price * i.qty for i in items), 2) if items else body.amount
    # Businesses never set or see the courier fee: the owner's fixed fee for that business applies.
    fee = b.default_fee if created_by == "business" else body.delivery_fee
    total = amount + fee
    o = Order(owner_id=owner_id, number=number, business_id=b.id, business_name=b.name,
              customer_name=body.customer_name, customer_phone=body.customer_phone,
              address=body.address, notes=body.notes, items=items, amount=amount, delivery_fee=fee,
              total=round(total, 2), history=[StatusEvent(status="nuevo")],
              # Nothing to collect from the customer -> the order is already paid.
              payment_method=body.payment_method if amount > 0 else "pagado",
              pickup_address=b.address, pickup_lat=b.lat, pickup_lng=b.lng, pickup_phone=b.phone,
              scheduled_for=body.scheduled_for, created_by=created_by)
    if body.dest_lat is not None and body.dest_lng is not None:
        o.dest_lat, o.dest_lng = body.dest_lat, body.dest_lng
    else:
        o.dest_lat, o.dest_lng = await geocode(body.address, (b.lat, b.lng) if b.lat is not None else None)
    if b.pricing_mode == "km" and o.dest_lat is not None and b.lat is not None:
        km = await route_km((b.lat, b.lng), (o.dest_lat, o.dest_lng))
        o.distance_km = km
        if created_by == "business" and km is not None:
            # Business orders: price by shortest road distance from pickup to delivery.
            o.delivery_fee = km_fee(b, km)
            o.total = round(amount + o.delivery_fee, 2)
    o.geo_tried = b.lat is not None
    o.geo_v = 2 if b.lat is not None else 0
    if body.courier_id:
        c = await get_courier(body.courier_id, owner_id)
        o.courier_id, o.courier_name = c.id, c.name
        o.assigned_at = now_iso()
    elif created_by == "business" or body.open:
        o.open = True
    res = await db.orders.insert_one(o.to_mongo())
    o.id = str(res.inserted_id)
    if o.courier_id:
        notify([o.courier_id], "Nueva tarea asignada", f"#{o.number:02d} · Recoger en {b.name}", "/courier")
    elif o.open:
        ids = [str(d["_id"]) for d in await db.users.find({"role": "courier", "owner_id": owner_id, "online": True}, {"_id": 1}).to_list(500)]
        notify(ids, "Nueva tarea disponible", f"#{o.number:02d} · {b.name}. ¡Acéptala antes que otro!", "/courier")
    if created_by == "business":
        notify([owner_id], f"Nuevo pedido de {b.name}", f"#{o.number:02d} · {o.customer_name}", f"/order/{o.id}")
    return o.model_dump()


async def get_order(order_id: str, q: dict) -> Order:
    d = await db.orders.find_one({"_id": oid(order_id), **q})
    if not d:
        raise HTTPException(404, "Orden no encontrada")
    return Order.from_mongo(d)


@api.get("/orders/{order_id}")
async def order_detail(order_id: str, u: User = Depends(owner_user)):
    await get_order(order_id, {"owner_id": u.id})
    doc = await ensure_coords(await db.orders.find_one({"_id": ObjectId(order_id)}))
    o = Order.from_mongo(doc).model_dump()
    o["courier"] = None
    if o["courier_id"] and ObjectId.is_valid(o["courier_id"]):
        cd = await db.users.find_one({"_id": ObjectId(o["courier_id"])})
        if cd:
            o["courier"] = User.from_mongo(cd).public()
    return o


async def set_status(o: Order, status: str) -> dict:
    ts = now_iso()
    await db.orders.update_one(
        {"_id": ObjectId(o.id)},
        {"$set": {"status": status, "updated_at": ts}, "$push": {"history": {"status": status, "at": ts}}},
    )
    return Order.from_mongo(await db.orders.find_one({"_id": ObjectId(o.id)})).model_dump()


CLOSED = ("entregado", "cancelado")


def check_transition(current: str, new: str):
    if current in CLOSED:
        raise HTTPException(400, "La orden ya está cerrada")
    if new != "cancelado" and STATUSES.index(new) <= STATUSES.index(current):
        raise HTTPException(400, "Cambio de estado no permitido")


@api.patch("/orders/{order_id}/status")
async def update_status(order_id: str, body: StatusIn, u: User = Depends(owner_user)):
    o = await get_order(order_id, {"owner_id": u.id})
    check_transition(o.status, body.status)
    return await set_status(o, body.status)


@api.patch("/orders/{order_id}/assign")
async def assign_courier(order_id: str, body: AssignIn, u: User = Depends(owner_user)):
    o = await get_order(order_id, {"owner_id": u.id})
    if o.status in CLOSED:
        raise HTTPException(400, "La orden ya está cerrada")
    name = None
    if body.courier_id:
        name = (await get_courier(body.courier_id, u.id)).name
    upd = {"courier_id": body.courier_id, "courier_name": name, "updated_at": now_iso(), "open": False}
    if body.courier_id != o.courier_id:
        upd["assigned_at"] = now_iso() if body.courier_id else None
    await db.orders.update_one({"_id": ObjectId(order_id)}, {"$set": upd})
    if body.courier_id and body.courier_id != o.courier_id:
        notify([body.courier_id], "Nueva tarea asignada", f"#{o.number:02d} · Recoger en {o.business_name}", "/courier")
    if o.courier_id and body.courier_id != o.courier_id:
        notify([o.courier_id], "Tarea retirada", f"#{o.number:02d} ya no está asignada a ti", "/courier")
    return await order_detail(order_id, u)


@api.patch("/orders/{order_id}/fee")
async def update_fee(order_id: str, body: FeeIn, u: User = Depends(owner_user)):
    o = await get_order(order_id, {"owner_id": u.id})
    if o.courier_paid:
        raise HTTPException(400, "Este envío ya se pagó al repartidor")
    fee = round(body.delivery_fee, 2)
    await db.orders.update_one({"_id": ObjectId(order_id)}, {"$set": {"delivery_fee": fee, "total": round(o.amount + fee, 2), "updated_at": now_iso()}})
    return await order_detail(order_id, u)


@api.patch("/orders/{order_id}/payment")
async def update_payment(order_id: str, body: PaymentIn, u: User = Depends(owner_user)):
    o = await get_order(order_id, {"owner_id": u.id})
    if o.status == "cancelado":
        raise HTTPException(400, "La orden está cancelada")
    await db.orders.update_one({"_id": ObjectId(order_id)}, {"$set": {"payment_method": body.payment_method}})
    return await order_detail(order_id, u)


def parse_range(start: str, end: str) -> tuple:
    try:
        s = datetime.fromisoformat(start).astimezone(timezone.utc).isoformat()
        e = datetime.fromisoformat(end).astimezone(timezone.utc).isoformat()
    except ValueError:
        raise HTTPException(400, "Fechas inválidas")
    return s, e


@api.get("/reports")
async def reports(start: str, end: str, u: User = Depends(owner_user)):
    s, e = parse_range(start, end)
    q = {"owner_id": u.id, "created_at": {"$gte": s, "$lt": e}}
    docs = await db.orders.find(q).sort("created_at", -1).to_list(3000)
    rows = await db.orders.aggregate([
        {"$match": q},
        {"$group": {
            "_id": {"status": "$status", "pm": {"$ifNull": ["$payment_method", "efectivo"]}},
            "count": {"$sum": 1}, "total": {"$sum": "$total"}, "fees": {"$sum": "$delivery_fee"},
        }},
    ]).to_list(100)
    revenue = fees = 0.0
    count = delivered = cancelled = 0
    by_payment = {p: 0.0 for p in PAYMENT_METHODS}
    by_courier: dict = {}
    for d in docs:
        if d["status"] == "cancelado":
            continue
        key = d.get("courier_id") or "none"
        c = by_courier.setdefault(key, {"courier_id": d.get("courier_id"), "name": d.get("courier_name") or "Sin repartidor", "count": 0, "total": 0.0})
        c["count"] += 1
        c["total"] = round(c["total"] + d.get("delivery_fee", 0), 2)
    for r in rows:
        count += r["count"]
        if r["_id"]["status"] == "cancelado":
            cancelled += r["count"]
            continue
        if r["_id"]["status"] == "entregado":
            delivered += r["count"]
        revenue += r["fees"]
        fees += r["fees"]
        pm = r["_id"]["pm"] if r["_id"]["pm"] in by_payment else "efectivo"
        by_payment[pm] += r["fees"]
    return {
        "orders": [Order.from_mongo(d).model_dump() for d in docs],
        "count": count,
        "delivered": delivered,
        "cancelled": cancelled,
        "revenue": round(revenue, 2),
        "fees": round(fees, 2),
        "by_payment": {k: round(v, 2) for k, v in by_payment.items()},
        "by_courier": sorted(by_courier.values(), key=lambda c: -c["total"]),
    }


@api.get("/orders/{order_id}/photo")
async def order_photo(order_id: str, token: str):
    payload = read_photo_token(token)
    d = await db.orders.find_one({"_id": oid(order_id)})
    if not d or not d.get("delivery_photo"):
        raise HTTPException(404, "Sin foto")
    uid, role = payload["sub"], payload["role"]
    if role == "business":
        bu = await db.users.find_one({"_id": oid(uid)})
        if not bu or bu.get("business_id") != d["business_id"]:
            raise HTTPException(404, "Sin foto")
    elif (role == "owner" and d["owner_id"] != tenant_id(await db.users.find_one({"_id": oid(uid)}) or {"role": "x"})) or (role == "courier" and d.get("courier_id") != uid):
        raise HTTPException(404, "Sin foto")
    data, ctype = await run_in_threadpool(get_object, d["delivery_photo"])
    if len(data) < 200:
        raise HTTPException(404, "Foto no disponible")
    return image_response(data, "private, max-age=86400")


@api.get("/dashboard")
async def dashboard(u: User = Depends(owner_user)):
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today = await db.orders.find({"owner_id": u.id, "created_at": {"$gte": start}}).to_list(2000)
    counts = {s: 0 for s in STATUSES}
    all_active = await db.orders.find({"owner_id": u.id, "status": {"$in": ["nuevo", "preparacion", "en_camino"]}}).to_list(2000)
    for d in all_active:
        counts[d["status"]] += 1
    revenue = sum(d.get("delivery_fee", 0) for d in today if d["status"] != "cancelado")
    delivered_today = sum(1 for d in today if d["status"] == "entregado")
    couriers_total = await db.users.count_documents({"role": "courier", "owner_id": u.id})
    couriers_online = await db.users.count_documents({"role": "courier", "owner_id": u.id, "online": True})
    recent = await db.orders.find({"owner_id": u.id, "status": {"$in": ["nuevo", "preparacion", "en_camino"]}}).sort("created_at", -1).to_list(8)
    return {
        "revenue_today": round(revenue, 2),
        "orders_today": len(today),
        "delivered_today": delivered_today,
        "counts": counts,
        "couriers_total": couriers_total,
        "couriers_online": couriers_online,
        "recent": [Order.from_mongo(d).model_dump() for d in recent],
    }


# ---------------- Courier payouts (delivery fees owed to each courier) ----------------
async def pending_for(courier_id: str) -> dict:
    rows = await db.orders.aggregate([
        {"$match": {"courier_id": courier_id, "status": "entregado", "courier_paid": {"$ne": True}}},
        {"$group": {"_id": None, "count": {"$sum": 1}, "fees": {"$sum": "$delivery_fee"}}},
    ]).to_list(1)
    r = rows[0] if rows else {"count": 0, "fees": 0}
    return {"pending_count": r["count"], "pending_total": round(r["fees"], 2)}


@api.get("/payouts")
async def payouts(u: User = Depends(owner_user)):
    out = []
    for d in await db.users.find({"role": "courier", "owner_id": u.id}).sort("name", 1).to_list(500):
        c = User.from_mongo(d)
        last = await db.payouts.find_one({"courier_id": c.id}, sort=[("at", -1)])
        out.append({
            "courier_id": c.id, "name": c.name, **(await pending_for(c.id)),
            "last_paid_at": last["at"] if last else None, "last_paid_amount": last["amount"] if last else None,
        })
    return out


@api.post("/payouts/{cid}")
async def pay_courier(cid: str, u: User = Depends(owner_user)):
    c = await get_courier(cid, u.id)
    p = await pending_for(c.id)
    if p["pending_count"] == 0:
        raise HTTPException(400, "No hay nada pendiente de pago")
    ts = now_iso()
    ids = [d["_id"] for d in await db.orders.find(
        {"courier_id": c.id, "status": "entregado", "courier_paid": {"$ne": True}}, {"_id": 1, "delivery_fee": 1}
    ).to_list(10000)]
    docs = await db.orders.find({"_id": {"$in": ids}}, {"delivery_fee": 1}).to_list(10000)
    amount = round(sum(d.get("delivery_fee", 0) for d in docs), 2)
    await db.orders.update_many({"_id": {"$in": ids}}, {"$set": {"courier_paid": True, "courier_paid_at": ts}})
    await db.payouts.insert_one({"owner_id": u.id, "courier_id": c.id, "courier_name": c.name, "amount": amount, "count": len(ids), "at": ts})
    return {"ok": True, "amount": amount, "count": len(ids)}


@api.get("/settings")
async def get_settings(u: User = Depends(owner_user)):
    d = await db.users.find_one({"_id": ObjectId(u.id)})
    return {"emergency_phones": norm_phones((d or {}).get("emergency_phones", []))}


@api.put("/settings")
async def put_settings(body: SettingsIn, u: User = Depends(owner_user)):
    phones = norm_phones(body.emergency_phones)
    await db.users.update_one({"_id": ObjectId(u.id)}, {"$set": {"emergency_phones": phones}})
    return {"emergency_phones": phones}


@api.get("/payouts/{cid}/history")
async def payout_history(cid: str, u: User = Depends(owner_user)):
    await get_courier(cid, u.id)
    docs = await db.payouts.find({"courier_id": cid, "owner_id": u.id}).sort("at", -1).to_list(100)
    return [{"amount": d["amount"], "count": d["count"], "at": d["at"]} for d in docs]


# ---------------- Courier side ----------------
@api.get("/courier/orders")
async def courier_orders(since: Optional[str] = None, u: User = Depends(courier_user)):
    active = await db.orders.find({"courier_id": u.id, "status": {"$in": ["nuevo", "preparacion", "en_camino"]}}).sort("created_at", 1).to_list(100)
    active = [await ensure_coords(d) for d in active]
    s = parse_range(since, since)[0] if since else datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    done = await db.orders.find({"courier_id": u.id, "status": "entregado", "updated_at": {"$gte": s}}).sort("updated_at", -1).to_list(200)
    biz_ids = list({ObjectId(d["business_id"]) for d in active + done if ObjectId.is_valid(d.get("business_id", ""))})
    bizs = {str(b["_id"]): b for b in await db.businesses.find({"_id": {"$in": biz_ids}}).to_list(200)}
    for d in active + done:
        b = bizs.get(d.get("business_id"), {})
        d["pickup_phone"] = b.get("phone", d.get("pickup_phone", ""))
        d["pickup_phones"] = norm_phones(b.get("phones") or ([b["phone"]] if b.get("phone") else []))
        d["business_photo"] = b.get("photo")
    cancelled = await db.orders.find({"courier_id": u.id, "status": "cancelado", "updated_at": {"$gte": s}}).sort("updated_at", -1).to_list(200)
    owner = await db.users.find_one({"_id": ObjectId(u.owner_id)}) if u.owner_id and ObjectId.is_valid(u.owner_id) else None
    return {
        "active": [Order.from_mongo(d).model_dump() for d in active],
        "delivered": [Order.from_mongo(d).model_dump() for d in done],
        "cancelled": [Order.from_mongo(d).model_dump() for d in cancelled],
        "emergency_phones": norm_phones((owner or {}).get("emergency_phones", [])),
        **(await pending_for(u.id)),
    }


@api.get("/courier/history")
async def courier_history(start: str, end: str, u: User = Depends(courier_user)):
    s, e = parse_range(start, end)
    q = {"courier_id": u.id, "status": "entregado", "updated_at": {"$gte": s, "$lt": e}}
    docs = await db.orders.find(q).sort("updated_at", -1).to_list(2000)
    agg = await db.orders.aggregate([
        {"$match": q},
        {"$group": {"_id": None, "count": {"$sum": 1}, "total": {"$sum": "$total"}, "fees": {"$sum": "$delivery_fee"}}},
    ]).to_list(1)
    t = agg[0] if agg else {"count": 0, "total": 0, "fees": 0}
    orders = [Order.from_mongo(d).model_dump() for d in docs]
    return {
        "orders": orders,
        "count": t["count"],
        "total_collected": round(t["fees"], 2),
        "total_fees": round(t["fees"], 2),
    }


@api.patch("/courier/orders/{order_id}/status")
async def courier_status(order_id: str, body: CourierStatusIn, u: User = Depends(courier_user)):
    if body.status not in ("en_camino", "entregado"):
        raise HTTPException(400, "Estado no permitido")
    o = await get_order(order_id, {"courier_id": u.id})
    check_transition(o.status, body.status)
    if body.status == "entregado" and body.note.strip():
        await db.orders.update_one({"_id": ObjectId(o.id)}, {"$set": {"delivery_note": body.note.strip()}})
    out = await set_status(o, body.status)
    biz_ids = [str(d["_id"]) for d in await db.users.find({"role": "business", "business_id": o.business_id}, {"_id": 1}).to_list(20)]
    msg = "recogido y en camino" if body.status == "en_camino" else "entregado"
    notify(biz_ids, f"Pedido #{o.number:02d} {msg}", f"{u.name} · {o.customer_name}", f"/biz-order/{o.id}")
    return out


@api.post("/courier/orders/{order_id}/incident")
async def courier_incident(order_id: str, body: IncidentIn, u: User = Depends(courier_user)):
    o = await get_order(order_id, {"courier_id": u.id})
    inc = {"type": body.type, "label": INCIDENT_LABEL[body.type], "note": body.note.strip(), "at": now_iso(), "by": u.name}
    await db.orders.update_one({"_id": ObjectId(o.id)}, {"$push": {"incidents": inc}, "$set": {"updated_at": now_iso()}})
    biz_ids = [str(d["_id"]) for d in await db.users.find({"role": "business", "business_id": o.business_id}, {"_id": 1}).to_list(20)]
    msg = f"{u.name}: {inc['label']}{' · ' + inc['note'] if inc['note'] else ''}"
    notify([o.owner_id], f"⚠️ Incidencia en #{o.number:02d}", msg, f"/order/{o.id}")
    if biz_ids:
        notify(biz_ids, f"⚠️ Incidencia en #{o.number:02d}", msg, f"/biz-order/{o.id}")
    return {"ok": True, "incident": inc}


# ---------------- Open tasks (any courier can accept) ----------------
@api.get("/courier/open-orders")
async def courier_open_orders(u: User = Depends(courier_user)):
    docs = await db.orders.find({"owner_id": u.owner_id, "open": True, "courier_id": None, "status": {"$in": ["nuevo", "preparacion"]}}).sort("created_at", 1).to_list(100)
    docs = [await ensure_coords(d) for d in docs]
    biz_ids = list({ObjectId(d["business_id"]) for d in docs if ObjectId.is_valid(d.get("business_id", ""))})
    photos = {str(b["_id"]): b.get("photo") for b in await db.businesses.find({"_id": {"$in": biz_ids}}, {"photo": 1}).to_list(200)}
    for d in docs:
        d["business_photo"] = photos.get(d.get("business_id"))
    return [Order.from_mongo(d).model_dump() for d in docs]


@api.post("/courier/orders/{order_id}/accept")
async def courier_accept(order_id: str, u: User = Depends(courier_user)):
    ts = now_iso()
    d = await db.orders.find_one_and_update(
        {"_id": oid(order_id), "owner_id": u.owner_id, "open": True, "courier_id": None, "status": {"$in": ["nuevo", "preparacion"]}},
        {"$set": {"courier_id": u.id, "courier_name": u.name, "open": False, "assigned_at": ts, "updated_at": ts}},
        return_document=ReturnDocument.AFTER,
    )
    if not d:
        raise HTTPException(409, "Otro repartidor ya aceptó esta tarea")
    o = Order.from_mongo(d)
    biz_ids = [str(x["_id"]) for x in await db.users.find({"role": "business", "business_id": o.business_id}, {"_id": 1}).to_list(20)]
    notify(biz_ids + [o.owner_id], f"Pedido #{o.number:02d} aceptado", f"Lo lleva {u.name}", f"/biz-order/{o.id}")
    return o.model_dump()


# ---------------- Business (comercio) side: no courier location exposed ----------------
def courier_card(d: dict) -> dict:
    return {"id": str(d["_id"]), "name": d["name"], "phone": d.get("phone"), "vehicle": d.get("vehicle"),
            "online": d.get("online", False), "has_photo": bool(d.get("profile_photo"))}


async def biz_business(u: User) -> Business:
    d = await db.businesses.find_one({"_id": oid(u.business_id)})
    if not d:
        raise HTTPException(404, "Comercio no encontrado")
    return Business.from_mongo(d)


def biz_order(d: dict) -> dict:
    # Businesses see the delivery fee and distance, but not courier payouts or coordinates.
    return Order.from_mongo(d).model_dump(exclude={"pickup_lat", "pickup_lng", "dest_lat", "dest_lng", "geo_tried", "geo_v", "courier_paid"})


class AddressIn(BaseModel):
    address: str = Field(min_length=4, max_length=300)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


async def change_address(o: Order, body: AddressIn, who: str) -> None:
    """Fix a wrong delivery address (even after the courier took it); re-price by km if applicable."""
    if o.status in ("entregado", "cancelado"):
        raise HTTPException(400, "El pedido ya está cerrado")
    lat, lng = (body.lat, body.lng) if body.lat is not None and body.lng is not None else await geocode(body.address, (o.pickup_lat, o.pickup_lng) if o.pickup_lat is not None else None)
    if lat is None:
        raise HTTPException(400, "No encontramos esa dirección en el mapa. Elígela de las sugerencias.")
    upd: dict = {"address": body.address.strip(), "dest_lat": lat, "dest_lng": lng, "updated_at": now_iso()}
    bd = await db.businesses.find_one({"_id": oid(o.business_id)}) if ObjectId.is_valid(o.business_id) else None
    if bd and bd.get("pricing_mode") == "km" and lat is not None and o.pickup_lat is not None:
        km = await route_km((o.pickup_lat, o.pickup_lng), (lat, lng))
        upd["distance_km"] = km
        if km is not None and not o.courier_paid:
            fee = km_fee(Business.from_mongo(bd), km)
            upd.update(delivery_fee=fee, total=round(o.amount + fee, 2))
    await db.orders.update_one({"_id": ObjectId(o.id)}, {"$set": upd})
    if o.courier_id:
        notify([o.courier_id], f"Dirección cambiada en #{o.number:02d}", f"{who}: {upd['address']}", "/courier")


@api.patch("/orders/{order_id}/address")
async def owner_change_address(order_id: str, body: AddressIn, u: User = Depends(owner_user)):
    await change_address(await get_order(order_id, {"owner_id": u.id}), body, "Administrador")
    return await order_detail(order_id, u)


@api.patch("/biz/orders/{order_id}/address")
async def biz_change_address(order_id: str, body: AddressIn, u: User = Depends(business_user)):
    o = await get_order(order_id, {"business_id": u.business_id})
    await change_address(o, body, o.business_name)
    return biz_order(await db.orders.find_one({"_id": ObjectId(order_id)}))


@api.get("/biz/me")
async def biz_me(u: User = Depends(business_user)):
    return (await biz_business(u)).model_dump(exclude={"default_fee", "km_base_price", "km_base_km", "km_extra_price", "pricing_mode"})


@api.get("/biz/quote")
async def biz_quote(lat: float, lng: float, u: User = Depends(business_user)):
    # Same price the order will get when sent (fixed fee or shortest road km).
    fee, km = await quote_for(await biz_business(u), lat, lng)
    return {"fee": fee, "distance_km": km}


@api.get("/biz/couriers")
async def biz_couriers(u: User = Depends(business_user)):
    docs = await db.users.find({"role": "courier", "owner_id": u.owner_id}).sort("name", 1).to_list(500)
    return [courier_card(d) for d in docs]


@api.get("/biz/orders")
async def biz_orders(start: Optional[str] = None, end: Optional[str] = None, u: User = Depends(business_user)):
    q: dict = {"business_id": u.business_id}
    if start and end:
        s, e = parse_range(start, end)
        q["created_at"] = {"$gte": s, "$lt": e}
    docs = await db.orders.find(q).sort("created_at", -1).to_list(2000)
    return [biz_order(d) for d in docs]


@api.post("/biz/orders")
async def biz_create_order(body: OrderIn, u: User = Depends(business_user)):
    b = await biz_business(u)
    body.business_id = b.id
    o = await build_order(body, u.owner_id, b, "business")
    return biz_order(await db.orders.find_one({"_id": ObjectId(o["id"])}))


@api.get("/biz/orders/{order_id}")
async def biz_order_detail(order_id: str, u: User = Depends(business_user)):
    d = await db.orders.find_one({"_id": oid(order_id), "business_id": u.business_id})
    if not d:
        raise HTTPException(404, "Orden no encontrada")
    o = biz_order(d)
    o["courier"] = None
    if o["courier_id"] and ObjectId.is_valid(o["courier_id"]):
        cd = await db.users.find_one({"_id": ObjectId(o["courier_id"])})
        if cd:
            o["courier"] = courier_card(cd)
    return o


@api.patch("/biz/orders/{order_id}/cancel")
async def biz_cancel(order_id: str, u: User = Depends(business_user)):
    o = await get_order(order_id, {"business_id": u.business_id})
    if o.status not in ("nuevo", "preparacion"):
        raise HTTPException(400, "Solo puedes cancelar pedidos que aún no se han recogido")
    await set_status(o, "cancelado")
    await db.orders.update_one({"_id": ObjectId(o.id)}, {"$set": {"open": False}})
    if o.courier_id:
        notify([o.courier_id], "Tarea cancelada", f"#{o.number:02d} fue cancelada por {o.business_name}", "/courier")
    return biz_order(await db.orders.find_one({"_id": ObjectId(o.id)}))


MAX_PHOTO = 8 * 1024 * 1024
PHOTO_TOKEN_MIN = 30


@api.post("/courier/orders/{order_id}/photo")
async def courier_photo(order_id: str, file: UploadFile = File(...), u: User = Depends(courier_user)):
    o = await get_order(order_id, {"courier_id": u.id})
    if o.status in CLOSED:
        raise HTTPException(400, "La orden ya está cerrada")
    data = await file.read()
    logger.info(f"Delivery photo upload order={order_id} bytes={len(data)}")
    return await save_photo(o, data, check_image(data))


async def save_photo(o: Order, data: bytes, ctype: str) -> dict:
    ext = "png" if ctype == "image/png" else "jpg"
    path = f"{APP_NAME}/uploads/{o.owner_id}/{uuid.uuid4()}.{ext}"
    res = await run_in_threadpool(put_object, path, data, ctype)
    stored, _ = await run_in_threadpool(get_object, res["path"])
    if len(stored) != len(data):
        logger.error(f"Photo verify failed order={o.id} sent={len(data)} stored={len(stored)}")
        raise HTTPException(502, "No se pudo guardar la foto, inténtalo de nuevo")
    await db.orders.update_one({"_id": ObjectId(o.id)}, {"$set": {"delivery_photo": res["path"]}})
    return {"ok": True}


@api.post("/courier/orders/{order_id}/photo-b64")
async def courier_photo_b64(order_id: str, body: PhotoB64In, u: User = Depends(courier_user)):
    o = await get_order(order_id, {"courier_id": u.id})
    if o.status in CLOSED:
        raise HTTPException(400, "La orden ya está cerrada")
    try:
        data = base64.b64decode(body.data.split(",")[-1])
    except Exception:
        raise HTTPException(400, "Foto inválida")
    logger.info(f"Delivery photo (b64) order={order_id} bytes={len(data)}")
    return await save_photo(o, data, check_image(data))


@api.post("/courier/location")
async def courier_location(body: LocationIn, u: User = Depends(courier_user)):
    await db.users.update_one({"_id": ObjectId(u.id)}, {"$set": {"lat": body.lat, "lng": body.lng, "location_at": now_iso(), "online": True}})
    return {"ok": True}


@api.post("/courier/online")
async def courier_online(body: OnlineIn, u: User = Depends(courier_user)):
    await db.users.update_one({"_id": ObjectId(u.id)}, {"$set": {"online": body.online}})
    return {"ok": True, "online": body.online}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- Seed ----------------
async def seed():
    await db.users.create_index([("role", 1), ("email", 1)])
    await db.users.create_index([("role", 1), ("phone", 1)])
    # One account per email and role (prevents duplicate admins with the same login).
    await db.users.create_index([("role", 1), ("email", 1)], unique=True, name="uniq_role_email",
                                partialFilterExpression={"email": {"$type": "string"}})
    await db.orders.create_index([("owner_id", 1), ("status", 1)])
    email = os.environ["ADMIN_EMAIL"].lower()
    password = os.environ["ADMIN_PASSWORD"]
    doc = await db.users.find_one({"role": "owner", "email": email})
    if not doc:
        owner = User(role="owner", name="Administrador", email=email, password_hash=hash_secret(password))
        res = await db.users.insert_one(owner.to_mongo())
        owner.id = str(res.inserted_id)
    else:
        # Never overwrite the admin password on restart: once changed in the app, it stays changed.
        owner = User.from_mongo(doc)
    if await db.businesses.count_documents({"owner_id": owner.id}):
        return
    catalog = {
        ("Café Aroma", "Cafetería", "Calle de Fuencarral 45, Madrid"): [("Café con leche", 2.5), ("Medialunas x3", 3.0), ("Tostado de jamón y queso", 5.5), ("Jugo de naranja", 3.2)],
        ("Pizzería Napoli", "Comida", "Calle Mayor 10, Madrid"): [("Pizza muzzarella", 9.0), ("Pizza napolitana", 10.5), ("Empanada de carne", 1.8), ("Gaseosa 1.5L", 2.8)],
        ("Farmacia Central", "Farmacia", "Calle de Alcalá 50, Madrid"): [("Ibuprofeno 400mg", 4.2), ("Alcohol en gel", 3.5), ("Vitamina C", 6.0)],
    }
    biz_products = []
    for (name, cat, addr), prods in catalog.items():
        b = Business(owner_id=owner.id, name=name, category=cat, address=addr, phone="1100000000")
        b.id = str((await db.businesses.insert_one(b.to_mongo())).inserted_id)
        plist = []
        for pn, pr in prods:
            p = Product(owner_id=owner.id, business_id=b.id, name=pn, price=pr)
            p.id = str((await db.products.insert_one(p.to_mongo())).inserted_id)
            plist.append(p)
        biz_products.append((b, plist))
    couriers = []
    for cname, phone, pin, veh, lat, lng in [
        ("Carlos Gómez", "1100000001", "123456", "Moto", 40.4183, -3.7030),
        ("Lucía Pérez", "1100000002", "654321", "Bicicleta", 40.4240, -3.6930),
    ]:
        if await db.users.find_one({"role": "courier", "phone": phone}):
            continue
        c = User(role="courier", name=cname, phone=phone, password_hash=hash_secret(pin), owner_id=owner.id,
                 vehicle=veh, online=True, lat=lat, lng=lng, location_at=now_iso())
        c.id = str((await db.users.insert_one(c.to_mongo())).inserted_id)
        couriers.append(c)
    samples = [
        (0, "María López", "Av. Rivadavia 2300, Depto 4B", "nuevo", None),
        (1, "Juan Martínez", "Calle Lavalle 845", "preparacion", 0),
        (1, "Sofía Díaz", "Av. Callao 1020", "en_camino", 0),
        (2, "Pedro Ruiz", "Calle Tucumán 300", "en_camino", 1),
        (0, "Ana Torres", "Av. Belgrano 1500", "entregado", 1),
    ]
    number = 1001
    for bi, cust, addr, status, ci in samples:
        b, plist = biz_products[bi]
        items = [OrderItem(product_id=p.id, name=p.name, price=p.price, qty=q) for p, q in zip(plist[:2], [2, 1])]
        hist = [StatusEvent(status=s) for s in STATUSES[: STATUSES.index(status) + 1]]
        o = Order(owner_id=owner.id, number=number, business_id=b.id, business_name=b.name, customer_name=cust,
                  customer_phone="1155550000", address=addr, items=items, delivery_fee=2.0,
                  total=round(sum(i.price * i.qty for i in items) + 2.0, 2), status=status, history=hist)
        if ci is not None and ci < len(couriers):
            o.courier_id, o.courier_name = couriers[ci].id, couriers[ci].name
        await db.orders.insert_one(o.to_mongo())
        number += 1


async def remove_demo_business_account():
    """The old demo business login had a public password; remove it (owner creates real ones)."""
    await db.users.delete_many({"role": "business", "email": "cafe@delivery.com"})


async def renumber_per_business():
    """One-time: number existing orders 1..n per business by creation date."""
    if await db.meta.find_one({"_id": "biz_numbering_v1"}):
        return
    for bid in await db.orders.distinct("business_id"):
        docs = await db.orders.find({"business_id": bid}, {"_id": 1}).sort("created_at", 1).to_list(100000)
        for i, d in enumerate(docs, 1):
            await db.orders.update_one({"_id": d["_id"]}, {"$set": {"number": i}})
        await db.counters.update_one({"_id": f"orders_biz_{bid}"}, {"$set": {"seq": len(docs)}}, upsert=True)
    await db.meta.insert_one({"_id": "biz_numbering_v1", "at": now_iso()})
    logger.info("Orders renumbered per business")


@app.on_event("startup")
async def startup():
    await seed()
    await remove_demo_business_account()
    await renumber_per_business()
    try:
        await run_in_threadpool(init_storage)
    except Exception as ex:
        logger.error(f"Storage init failed: {ex}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
