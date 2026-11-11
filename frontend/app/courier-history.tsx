import { useQuery } from "@tanstack/react-query";
import { format, isSameDay, startOfDay } from "date-fns";
import { es } from "date-fns/locale";
import { useRouter } from "expo-router";
import { useMemo, useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, cap, money, Order, plural, num } from "@/src/api";
import { CalendarSheet } from "@/src/components/CalendarSheet";
import { Chip, EmptyState, ErrorState, Ionicons, Loading } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { isFuture, Period, PERIOD_LABEL, periodLabel, periodRange, shiftPeriod } from "@/src/period";
import { DateRange, RangePicker, rangeDates, todayRange } from "@/src/components/RangePicker";
import { makeStyles, useTheme } from "@/src/theme";

type History = { orders: Order[]; count: number; total_collected: number; total_fees: number };
const PERIODS: Period[] = ["dia", "semana", "quincena", "mes"];
// Real delivery time from the status history (updated_at can change after delivery).
const deliveredAt = (o: Order) => new Date([...(o.history ?? [])].reverse().find((h) => h.status === "entregado")?.at ?? o.updated_at);


export default function CourierHistory() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [period, setPeriod] = useState<Period | "rango">("dia");
  const [date, setDate] = useState(() => startOfDay(new Date()));
  const [calendar, setCalendar] = useState(false);
  const [range, setRange] = useState<DateRange>(todayRange);

  const [start, end] = period === "rango" ? rangeDates(range) : periodRange(period, date);
  const q = useQuery({
    queryKey: ["courier-history", start.toISOString(), end.toISOString()],
    queryFn: () => api<History>(`/courier/history?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`),
  });

  const byDay = useMemo(() => {
    const map = new Map<string, { day: Date; count: number; collected: number; fees: number }>();
    for (const o of q.data?.orders ?? []) {
      const day = startOfDay(new Date(o.updated_at));
      const k = day.toISOString();
      const cur = map.get(k) ?? { day, count: 0, collected: 0, fees: 0 };
      cur.count += 1;
      cur.collected += o.delivery_fee;
      cur.fees += o.delivery_fee;
      map.set(k, cur);
    }
    return [...map.values()].sort((a, b) => b.day.getTime() - a.day.getTime());
  }, [q.data]);

  const nextDisabled = period === "rango" || isFuture(shiftPeriod(period, date, 1));

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <View style={s.titleRow}>
          <Pressable testID="back-button" onPress={() => router.back()} style={s.iconBtn}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <Text style={s.title}>Mis entregas</Text>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipRow} contentContainerStyle={s.chips}>
          {PERIODS.map((p) => (
            <Chip key={p} testID={`period-chip-${p}`} label={PERIOD_LABEL[p]} selected={period === p} onPress={() => setPeriod(p)} />
          ))}
          <Chip testID="period-chip-rango" label="Entre fechas" selected={period === "rango"} onPress={() => setPeriod("rango")} />
        </ScrollView>
        {period === "rango" ? (
          <View style={{ paddingHorizontal: space.lg, paddingBottom: space.sm }}>
            <RangePicker testID="history-range" value={range} onChange={setRange} />
          </View>
        ) : (
        <View style={s.dateRow}>
          <Pressable testID="period-prev" onPress={() => setDate(shiftPeriod(period, date, -1))} style={s.iconBtn}>
            <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
          </Pressable>
          <Pressable testID="open-calendar-button" onPress={() => setCalendar(true)} style={s.dateBtn}>
            <Ionicons name="calendar-outline" size={18} color={colors.brandPrimary} />
            <Text testID="period-label" style={s.dateText} numberOfLines={1}>{periodLabel(period, date)}</Text>
          </Pressable>
          <Pressable testID="period-next" disabled={nextDisabled} onPress={() => setDate(shiftPeriod(period, date, 1))} style={[s.iconBtn, nextDisabled && { opacity: 0.3 }]}>
            <Ionicons name="chevron-forward" size={22} color={colors.onSurface} />
          </Pressable>
        </View>
        )}
      </View>

      {q.isLoading ? (
        <Loading />
      ) : q.isError ? (
        <ErrorState message="No pudimos cargar tus entregas" onRetry={() => q.refetch()} />
      ) : (
        <ScrollView
          contentContainerStyle={[s.content, { paddingBottom: insets.bottom + space.xl }]}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => { q.refetch(); }} tintColor={colors.brandPrimary} />}
        >
          <View style={s.summary}>
            <Text style={s.summaryLabel}>Total de envíos</Text>
            <Text testID="history-total-collected" style={s.summaryValue}>{money(q.data?.total_collected ?? 0)}</Text>
            <View style={s.summaryRow}>
              <View style={s.summaryItem}>
                <Text style={s.summarySmallLabel}>Órdenes entregadas</Text>
                <Text testID="history-count" style={s.summarySmall}>{q.data?.count ?? 0}</Text>
              </View>
            </View>
          </View>

          {period !== "dia" && byDay.length > 0 && (
            <>
              <Text style={s.section}>Total por día</Text>
              <View style={s.card}>
                {byDay.map((d, i) => (
                  <Pressable
                    key={d.day.toISOString()}
                    testID={`history-day-${format(d.day, "yyyy-MM-dd")}`}
                    onPress={() => {
                      setDate(d.day);
                      setPeriod("dia");
                    }}
                    style={[s.dayRow, i > 0 && s.divider]}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={s.dayName}>{cap(format(d.day, "EEEE d MMM", { locale: es }))}</Text>
                      <Text style={s.muted}>{plural(d.count, "orden", "órdenes")}</Text>
                    </View>
                    <Text style={s.dayTotal}>{money(d.collected)}</Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>
                ))}
              </View>
            </>
          )}

          <Text style={s.section}>Pedidos realizados</Text>
          {q.data?.orders.length === 0 ? (
            <EmptyState testID="history-empty" title="Sin entregas en este periodo" subtitle="Elige otra fecha o periodo." />
          ) : (
            <View style={s.card}>
              {q.data?.orders.map((o, i) => (
                <View key={o.id} testID={`history-order-${o.number}`} style={[s.orderRow, i > 0 && s.divider]}>
                  <Ionicons name="checkmark-circle" size={22} color={colors.success} />
                  <View style={{ flex: 1 }}>
                    <Text style={s.orderTitle} numberOfLines={1}>#{num(o.number)} · {o.business_name}</Text>
                    <Text style={s.muted} numberOfLines={1}>
                      Entregado {period === "dia" || isSameDay(start, deliveredAt(o))
                        ? `a las ${format(deliveredAt(o), "HH:mm")}`
                        : format(deliveredAt(o), "d MMM, HH:mm", { locale: es })}{" "}
                      · {o.customer_name}
                    </Text>
                    <Text style={s.muted} numberOfLines={2}>{o.address}</Text>
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={s.orderTotal}>{money(o.delivery_fee)}</Text>
                    <Text style={s.muted}>envío</Text>
                  </View>
                </View>
              ))}
            </View>
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
  summaryItem: { gap: 2 },
  summarySmallLabel: { fontFamily: font.medium, fontSize: 12, color: c.onBrandPrimary, opacity: 0.8 },
  summarySmall: { fontFamily: font.bold, fontSize: 18, color: c.onBrandPrimary },
  section: { fontFamily: font.bold, fontSize: 18, color: c.onSurface, marginTop: space.sm },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, paddingHorizontal: space.lg },
  divider: { borderTopWidth: 1, borderTopColor: c.divider },
  dayRow: { flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 60, paddingVertical: space.sm },
  dayName: { fontFamily: font.bold, fontSize: 15, color: c.onSurface },
  dayTotal: { fontFamily: font.extrabold, fontSize: 16, color: c.onSurface },
  muted: { fontFamily: font.medium, fontSize: 13, color: c.muted },
  orderRow: { flexDirection: "row", alignItems: "center", gap: space.md, paddingVertical: space.md },
  orderTitle: { fontFamily: font.bold, fontSize: 15, color: c.onSurface },
  orderTotal: { fontFamily: font.extrabold, fontSize: 15, color: c.onSurface },
}));
