import { OrderStatus, PaymentMethod } from "@/src/api";
import { ThemeColors } from "@/src/theme";

export const PAYMENT_METHODS: PaymentMethod[] = ["efectivo", "datafono", "pagado"];
export const PAYMENT_LABEL: Record<PaymentMethod, string> = {
  pagado: "Ya pagado",
  efectivo: "Efectivo",
  datafono: "Datáfono",
};
export const PAYMENT_ICON = {
  pagado: "checkmark-done-circle-outline",
  efectivo: "cash-outline",
  datafono: "card-outline",
} as const;

export const STATUS_FLOW: OrderStatus[] = ["nuevo", "preparacion", "en_camino", "entregado"];

export const STATUS_LABEL: Record<OrderStatus, string> = {
  nuevo: "Nuevo",
  preparacion: "En preparación",
  en_camino: "En camino",
  entregado: "Entregado",
  cancelado: "Cancelado",
};

export function statusColor(s: OrderStatus, c: ThemeColors) {
  return {
    nuevo: c.info,
    preparacion: c.warning,
    en_camino: c.brandPrimary,
    entregado: c.success,
    cancelado: c.error,
  }[s];
}

export function nextStatus(s: OrderStatus): OrderStatus | null {
  const i = STATUS_FLOW.indexOf(s);
  return i >= 0 && i < STATUS_FLOW.length - 1 ? STATUS_FLOW[i + 1] : null;
}


// Minutes from pickup (en_camino) to delivery (entregado), or null if not both happened.
export function deliveryMinutes(history: { status: string; at: string }[]): number | null {
  const picked = history.find((h) => h.status === "en_camino");
  const done = [...history].reverse().find((h) => h.status === "entregado");
  if (!picked || !done) return null;
  return Math.max(0, Math.floor((new Date(done.at).getTime() - new Date(picked.at).getTime()) / 60000));
}

export function durationLabel(min: number): string {
  if (min < 1) return "menos de 1 min";
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h ${min % 60} min`;
}
