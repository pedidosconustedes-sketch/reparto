import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { Order, num } from "@/src/api";
import { ring } from "@/src/alert";
import { useToast } from "@/src/components/ui";

// Rings + shows a toast when a courier reports a new incident on any of these orders (while the app is open).
export function useIncidentAlert(orders: Order[] | undefined) {
  const toast = useToast();
  const qc = useQueryClient();
  const prev = useRef<Map<string, number> | null>(null);
  useEffect(() => {
    if (!orders) return;
    const cur = new Map(orders.map((o) => [o.id, o.incidents?.length ?? 0]));
    const p = prev.current;
    prev.current = cur;
    if (!p) return;
    const fresh = orders.filter((o) => (o.incidents?.length ?? 0) > (p.get(o.id) ?? 0));
    if (!fresh.length) return;
    ring();
    // Refresh the lists now so the card banner shows together with the toast.
    ["orders", "dashboard", "biz-orders"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    const o = fresh[0];
    const inc = o.incidents![o.incidents!.length - 1];
    toast(`⚠️ Incidencia #${num(o.number)} · ${inc.by}: ${inc.label}${inc.note ? ` — ${inc.note}` : ""}`, "error");
  }, [orders, toast, qc]);
}
