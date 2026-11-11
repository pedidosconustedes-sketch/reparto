import { addDays, addMonths, format, isAfter, startOfDay, startOfMonth, startOfWeek } from "date-fns";
import { es } from "date-fns/locale";

import { cap } from "@/src/api";

export type Period = "dia" | "semana" | "quincena" | "mes";

export const PERIOD_LABEL: Record<Period, string> = {
  dia: "Día",
  semana: "Semana",
  quincena: "Quincena",
  mes: "Mes",
};

// Returns [start, end) in the device's local time.
export function periodRange(p: Period, d: Date): [Date, Date] {
  const y = d.getFullYear();
  const m = d.getMonth();
  if (p === "dia") {
    const s = startOfDay(d);
    return [s, addDays(s, 1)];
  }
  if (p === "semana") {
    const s = startOfWeek(d, { weekStartsOn: 1 });
    return [s, addDays(s, 7)];
  }
  if (p === "quincena") {
    return d.getDate() <= 15 ? [new Date(y, m, 1), new Date(y, m, 16)] : [new Date(y, m, 16), new Date(y, m + 1, 1)];
  }
  const s = startOfMonth(d);
  return [s, addMonths(s, 1)];
}

export function shiftPeriod(p: Period, d: Date, dir: 1 | -1): Date {
  const [s, e] = periodRange(p, d);
  let next: Date;
  if (p === "mes") next = addMonths(d, dir);
  else if (p === "dia") next = addDays(d, dir);
  else next = dir === 1 ? e : addDays(s, -1);
  const today = startOfDay(new Date());
  return isAfter(next, today) ? today : next;
}

export function periodLabel(p: Period, d: Date): string {
  return cap(rawLabel(p, d));
}

function rawLabel(p: Period, d: Date): string {
  const [s, e] = periodRange(p, d);
  const last = addDays(e, -1);
  if (p === "dia") return format(d, "EEEE d 'de' MMMM yyyy", { locale: es });
  if (p === "semana") return `${format(s, "d MMM", { locale: es })} – ${format(last, "d MMM yyyy", { locale: es })}`;
  if (p === "quincena") return `${s.getDate() === 1 ? "1ª" : "2ª"} quincena de ${format(s, "MMMM yyyy", { locale: es })}`;
  return format(s, "MMMM yyyy", { locale: es });
}

export const isFuture = (d: Date) => isAfter(startOfDay(d), startOfDay(new Date()));
