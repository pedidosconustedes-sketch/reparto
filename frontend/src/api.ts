import { storage } from "@/src/utils/storage";

export const BASE = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;
export const TOKEN_KEY = "auth_token";

export type OrderStatus = "nuevo" | "preparacion" | "en_camino" | "entregado" | "cancelado";
export type PaymentMethod = "pagado" | "efectivo" | "datafono";

// Photos use a short-lived photo-only token, never the login token, in the image URL.
let photoTok: { token: string; at: number } | null = null;
let photoTokReq: Promise<string> | null = null;
export function clearPhotoToken() {
  photoTok = null;
  photoTokReq = null;
}
async function getPhotoToken() {
  if (photoTok && Date.now() - photoTok.at < 20 * 60 * 1000) return photoTok.token;
  // Share one request between all photos on screen.
  photoTokReq ??= api<{ token: string }>("/photo-token")
    .then((r) => {
      photoTok = { token: r.token, at: Date.now() };
      return r.token;
    })
    .finally(() => {
      photoTokReq = null;
    });
  return photoTokReq;
}

export async function photoUrl(orderId: string) {
  return `${BASE}/orders/${orderId}/photo?token=${await getPhotoToken()}`;
}

export async function userPhotoUrl(userId: string, v?: string | null) {
  return `${BASE}/users/${userId}/photo?token=${await getPhotoToken()}&v=${encodeURIComponent(v ?? "")}`;
}

export async function businessPhotoUrl(businessId: string, v?: string | null) {
  return `${BASE}/businesses/${businessId}/photo?token=${await getPhotoToken()}&v=${encodeURIComponent(v ?? "")}`;
}

export type CourierCard = { id: string; name: string; phone?: string | null; vehicle?: string | null; online: boolean; has_photo: boolean };

export type User = {
  id: string;
  role: "owner" | "courier" | "business";
  business_id?: string | null;
  profile_photo?: string | null;
  is_main?: boolean;
  linked?: boolean;
  parent_id?: string | null;
  name: string;
  email?: string | null;
  phone?: string | null;
  vehicle?: string | null;
  online: boolean;
  lat?: number | null;
  lng?: number | null;
  location_at?: string | null;
  active_orders?: number;
};

export type Business = {
  id: string;
  name: string;
  category: string;
  address: string;
  phone: string;
  account_email?: string | null;
  default_fee?: number;
  photo?: string | null;
  pricing_mode?: "fixed" | "km";
  km_base_price?: number;
  km_base_km?: number;
  km_extra_price?: number;
  phones?: { name: string; phone: string }[];
  lat?: number | null;
  lng?: number | null;
  product_count?: number;
  active_orders?: number;
};

export type Product = { id: string; business_id: string; name: string; price: number; available: boolean };

export type OrderItem = { product_id?: string; name: string; price: number; qty: number };

export type Order = {
  id: string;
  number: number;
  business_id: string;
  business_name: string;
  customer_name: string;
  customer_phone: string;
  address: string;
  notes: string;
  items: OrderItem[];
  amount?: number;
  delivery_fee: number;
  total: number;
  courier_paid?: boolean;
  business_photo?: string | null;
  pickup_phones?: { name: string; phone: string }[];
  distance_km?: number | null;
  incidents?: { type: string; label: string; note: string; at: string; by: string }[];
  status: OrderStatus;
  courier_id?: string | null;
  courier_name?: string | null;
  courier?: (User & { has_photo?: boolean }) | null;
  open?: boolean;
  created_by?: "owner" | "business";
  history: { status: OrderStatus; at: string }[];
  payment_method: PaymentMethod;
  pickup_phone?: string;
  assigned_at?: string | null;
  scheduled_for?: string | null;
  pickup_address?: string;
  pickup_lat?: number | null;
  pickup_lng?: number | null;
  dest_lat?: number | null;
  dest_lng?: number | null;
  delivery_note?: string;
  delivery_photo?: string | null;
  created_at: string;
  updated_at: string;
};

export type Dashboard = {
  revenue_today: number;
  orders_today: number;
  delivered_today: number;
  counts: Record<OrderStatus, number>;
  couriers_total: number;
  couriers_online: number;
  recent: Order[];
};

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export async function api<T>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const token = await storage.secureGet<string | null>(TOKEN_KEY, null);
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      method: opts.method ?? "GET",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new Error("Sin conexión. Revisa tu internet.");
  }
  const data = await res.json().catch(() => null);
  if (res.status === 401 && token) onUnauthorized?.();
  if (!res.ok) {
    const d = data?.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? "Revisa los datos ingresados" : "Algo salió mal");
  }
  return data as T;
}

export const num = (n: number) => String(n).padStart(2, "0");

export const money = (n: number) => {
  const [int, dec] = Math.abs(n).toFixed(2).split(".");
  return `${n < 0 ? "-" : ""}${int.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${dec} €`;
};

export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
