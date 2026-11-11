import { useQuery } from "@tanstack/react-query";
import { format, startOfDay } from "date-fns";
import { es } from "date-fns/locale";
import { useRouter } from "expo-router";
import { useMemo, useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, cap, money, Order, PaymentMethod, plural } from "@/src/api";
import { CalendarSheet } from "@/src/components/CalendarSheet";
import { OrderCard } from "@/src/components/OrderCard";
import { DateRange, RangePicker, rangeDates, todayRange } from "@/src/components/RangePicker";
import { Chip, EmptyState, ErrorState, Ionicons, Loading } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { isFuture, Period, PERIOD_LABEL, periodLabel, periodRange, shiftPeriod } from "@/src/period";
import { makeStyles, useTheme } from "@/src/theme";

type Report = {
  orders: Order[];
  count: number;
  delivered: number;
  cancelled: number;
  revenue: number;
  fees: number;
  by_payment: Record<PaymentMethod, number>;
  by_courier: { courier_id: string | null; name: string; count: number; total: number }[];
};
const PERIODS: Period[] = ["dia", "semana", "quincena", "mes"];

export default function Reports() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [period, setPeriod] = useState<Period | "rango">("mes");
  const [date, setDate] = useState(() => startOfDay(new Date()));
  const [calendar, setCalendar] = useState(false);
  const [range, setRange] = useState<DateRange>(todayRange);

  const [start, end] = period === "rango" ? rangeDates(range) : periodRange(period, date);
  const q = useQuery({
    queryKey: ["reports", start.toISOString(), end.toISOString()],
    queryFn: () => api<Report>(`/reports?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`),
  });

  const byDay = useMemo(() => {
    const map = new Map<string, { day: Date; count: number; total: number }>();
    for (const o of q.data?.orders ?? []) {
      if (o.status === "cancelado") continue;
      const day = startOfDay(new Date(o.created_at));
      const k = day.toISOString();
      const cur = map.get(k) ?? { day, count: 0, total: 0 };
      cur.count += 1;
      cur.total += o.delivery_fee;
      map.set(k, cur);
    }
    return [...map.values()].sort((a, b) => b.day.getTime() - a.day.getTime());
  }, [q.data]);

  const nextDisabled = period === "rango" || isFuture(shiftPeriod(period, date, 1));
  const [courierFilter, setCourierFilter] = useState<string | null>(null);
  const orders = (q.data?.orders ?? []).filter((o) => !courierFilter || (o.courier_id ?? "none") === courierFilter);

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <View style={s.titleRow}>
          <Pressable testID="back-button" onPress={() => router.back()} style={s.iconBtn}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <Text style={s.title}>Reportes</Text>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipRow} contentContainerStyle={s.chips}>
          {PERIODS.map((p) => (
            <Chip key={p} testID={`report-period-${p}`} label={PERIOD_LABEL[p]} selected={period === p} onPress={() => setPeriod(p)} />
          ))}
          <Chip testID="report-period-rango" label="Entre fechas" selected={period === "rango"} onPress={() => setPeriod("rango")} />
        </ScrollView>
        {period === "rango" ? (
          <View style={{ paddingHorizontal: space.lg }}>
            <RangePicker testID="report-range" value={range} onChange={setRange} />
          </View>
        ) : (
        <View style={s.dateRow}>
          <Pressable testID="report-prev" onPress={() => setDate(shiftPeriod(period, date, -1))} style={s.iconBtn}>
            <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
          </Pressable>
          <Pressable testID="report-open-calendar" onPress={() => setCalendar(true)} style={s.dateBtn}>
            <Ionicons name="calendar-outline" size={18} color={colors.brandPrimary} />
            <Text testID="report-period-label" style={s.dateText} numberOfLines={1}>{periodLabel(period, date)}</Text>
          </Pressable>
          <Pressable testID="report-next" disabled={nextDisabled} onPress={() => setDate(shiftPeriod(period, date, 1))} style={[s.iconBtn, nextDisabled && { opacity: 0.3 }]}>
            <Ionicons name="chevron-forward" size={22} color={colors.onSurface} />
          </Pressable>
        </View>
        )}
      </View>

      {q.isLoading ? (
        <Loading />
      ) : q.isError || !q.data ? (
        <ErrorState message="No pudimos cargar el reporte" onRetry={() => q.refetch()} />
      ) : (
        <ScrollView
          contentContainerStyle={[s.content, { paddingBottom: insets.bottom + space.xl }]}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => { q.refetch(); }} tintColor={colors.brandPrimary} />}
        >
          <View style={s.summary}>
            <Text style={s.summaryLabel}>Total de envíos</Text>
            <Text testID="report-revenue" style={s.summaryValue}>{money(q.data.revenue)}</Text>
            <View style={s.summaryRow}>
              <View>
                <Text style={s.smallLabel}>Pedidos</Text>
                <Text testID="report-count" style={s.small}>{q.data.count}</Text>
              </View>
              <View>
                <Text style={s.smallLabel}>Entregados</Text>
                <Text testID="report-delivered" style={s.small}>{q.data.delivered}</Text>
              </View>
            </View>
            {q.data.cancelled > 0 && <Text style={s.smallLabel}>{plural(q.data.cancelled, "pedido cancelado", "pedidos cancelados")} (no suman)</Text>}
          </View>


          {q.data.by_courier.length > 0 && (
            <>
              <Text style={s.section}>Por repartidor</Text>
              <View style={s.card}>
                {q.data.by_courier.map((c, i) => {
                  const key = c.courier_id ?? "none";
                  const sel = courierFilter === key;
                  return (
                    <Pressable
                      key={key}
                      testID={`report-courier-${key}`}
                      onPress={() => setCourierFilter(sel ? null : key)}
                      style={[s.dayRow, i > 0 && s.divider, sel && { backgroundColor: colors.brandTertiary, marginHorizontal: -space.lg, paddingHorizontal: space.lg }]}
                    >
                      <Ionicons name={c.courier_id ? "bicycle-outline" : "help-circle-outline"} size={20} color={colors.brandPrimary} />
                      <View style={{ flex: 1 }}>
                        <Text style={s.dayName}>{c.name}</Text>
                        <Text style={s.muted}>{plural(c.count, "orden", "órdenes")}{sel ? " · filtrando" : ""}</Text>
                      </View>
                      <Text testID={`report-courier-total-${key}`} style={s.dayTotal}>{money(c.total)}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </>
          )}

          {period !== "dia" && byDay.length > 0 && (
            <>
              <Text style={s.section}>Total por día</Text>
              <View style={s.card}>
                {byDay.map((d, i) => (
                  <Pressable
                    key={d.day.toISOString()}
                    testID={`report-day-${format(d.day, "yyyy-MM-dd")}`}
                    onPress={() => {
                      setDate(d.day);
                      setPeriod("dia");
                    }}
                    style={[s.dayRow, i > 0 && s.divider]}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={s.dayName}>{cap(format(d.day, "EEEE d MMM", { locale: es }))}</Text>
                      <Text style={s.muted}>{plural(d.count, "pedido", "pedidos")}</Text>
                    </View>
                    <Text style={s.dayTotal}>{money(d.total)}</Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>
                ))}
              </View>
            </>
          )}

          <Text style={s.section}>Pedidos ({orders.length})</Text>
          {orders.length === 0 ? (
            <EmptyState testID="report-empty" title="Sin pedidos en este periodo" subtitle="Elige otra fecha o periodo." />
          ) : (
            orders.map((o, i) => <OrderCard key={o.id} order={o} index={i} />)
          )}
        </ScrollView>
      )}

      <CalendarSheet visible={calendar} value={date} onClose={() => setCalendar(false)} onSelect={(d) => setDate(startOfDay(d))} />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.divider, paddingBottom: space.sm },
  titleRow: { flexDirection: "row", alignItems: "center", gap: space.xs, paddingHorizontal: space.sm },
  title: { fontFamily: font.extrabold, fontSize: 22, color: c.onSurface },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  chipRow: { height: 56, flexGrow: 0 },
  chips: { gap: space.sm, paddingHorizontal: space.lg, alignItems: "center" },
  dateRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: space.sm },
  dateBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: space.sm, height: 44, borderRadius: radius.md, backgroundColor: c.brandTertiary, paddingHorizontal: space.md },
  dateText: { fontFamily: font.bold, fontSize: 14, color: c.onBrandTertiary, flexShrink: 1 },
  content: { padding: space.lg, gap: space.md },
  summary: { backgroundColor: c.brandPrimary, borderRadius: radius.lg, padding: space.xl, gap: space.xs },
  summaryLabel: { fontFamily: font.semibold, fontSize: 14, color: c.onBrandPrimary, opacity: 0.85 },
  summaryValue: { fontFamily: font.extrabold, fontSize: 36, color: c.onBrandPrimary, letterSpacing: -0.5 },
  summaryRow: { flexDirection: "row", gap: space.xl, marginTop: space.sm },
  smallLabel: { fontFamily: font.medium, fontSize: 12, color: c.onBrandPrimary, opacity: 0.8 },
  small: { fontFamily: font.bold, fontSize: 18, color: c.onBrandPrimary },
  payGrid: { flexDirection: "row", gap: space.sm },
  payCard: { flex: 1, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, padding: space.md, gap: 4 },
  payValue: { fontFamily: font.extrabold, fontSize: 15, color: c.onSurface },
  section: { fontFamily: font.bold, fontSize: 18, color: c.onSurface, marginTop: space.sm },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, paddingHorizontal: space.lg },
  divider: { borderTopWidth: 1, borderTopColor: c.divider },
  dayRow: { flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 60, paddingVertical: space.sm },
  dayName: { fontFamily: font.bold, fontSize: 15, color: c.onSurface },
  dayTotal: { fontFamily: font.extrabold, fontSize: 16, color: c.onSurface },
  muted: { fontFamily: font.medium, fontSize: 13, color: c.muted },
}));
