import { useQuery, useQueryClient } from "@tanstack/react-query";
import { format, startOfDay } from "date-fns";
import { es } from "date-fns/locale";
import { useRouter, Redirect } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Business, money, Order, num } from "@/src/api";
import { ring } from "@/src/alert";
import { useAuth } from "@/src/auth";
import { ChangePasswordSheet } from "@/src/components/ChangePasswordSheet";
import { IncidentBanner } from "@/src/components/IncidentBanner";
import { useIncidentAlert } from "@/src/incidentAlert";
import { BizPhoto } from "@/src/components/BizPhoto";
import { CalendarSheet } from "@/src/components/CalendarSheet";
import { ProfilePhotoSheet } from "@/src/components/ProfilePhotoSheet";
import { isFuture, Period, PERIOD_LABEL, periodLabel, periodRange, shiftPeriod } from "@/src/period";
import { DateRange, RangePicker, rangeDates, todayRange } from "@/src/components/RangePicker";
import { Button, Chip, EmptyState, ErrorState, Ionicons, Loading, StatusBadge, useToast } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

const PERIODS: Period[] = ["dia", "semana", "quincena", "mes"];

const ACTIVE = ["nuevo", "preparacion", "en_camino"];

export default function BusinessHome() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const { user, loading, signOut } = useAuth();
  const qc = useQueryClient();
  const isBiz = user?.role === "business";
  const [pwOpen, setPwOpen] = useState(false);
  const me = useQuery({ queryKey: ["biz-me"], queryFn: () => api<Business>("/biz/me"), enabled: isBiz });
  const q = useQuery({ queryKey: ["biz-orders"], queryFn: () => api<Order[]>("/biz/orders"), refetchInterval: 8000, enabled: isBiz });
  // History filter: any date / period.
  const [period, setPeriod] = useState<Period | "todos" | "rango">("todos");
  const [date, setDate] = useState(() => startOfDay(new Date()));
  const [calendar, setCalendar] = useState(false);
  const [photoOpen, setPhotoOpen] = useState(false);
  const [range, setRange] = useState<DateRange>(todayRange);
  const [range0, range1] = period === "todos" ? [null, null] : period === "rango" ? rangeDates(range) : periodRange(period, date);
  const hist = useQuery({
    queryKey: ["biz-orders", "range", range0?.toISOString(), range1?.toISOString()],
    queryFn: () => api<Order[]>(`/biz/orders?start=${encodeURIComponent(range0!.toISOString())}&end=${encodeURIComponent(range1!.toISOString())}`),
    enabled: isBiz && period !== "todos",
  });

  useIncidentAlert(q.data);

  // Alert when a courier accepts one of my open orders.
  const prev = useRef<Map<string, string | null | undefined> | null>(null);
  useEffect(() => {
    if (!q.data) return;
    const cur = new Map(q.data.map((o) => [o.id, o.courier_name]));
    const p = prev.current;
    prev.current = cur;
    if (!p) return;
    const accepted = q.data.filter((o) => o.courier_name && p.has(o.id) && !p.get(o.id));
    if (accepted.length) {
      ring();
      toast(`${accepted[0].courier_name} aceptó el pedido #${num(accepted[0].number)}`);
    }
  }, [q.data, toast]);

  if (loading) return <Loading />;
  if (!isBiz) return <Redirect href="/" />;

  const active = (q.data ?? []).filter((o) => ACTIVE.includes(o.status));
  const pastSource = period === "todos" ? q.data ?? [] : hist.data ?? [];
  const done = pastSource.filter((o) => !ACTIVE.includes(o.status));
  const nextDisabled = period === "rango" || (period !== "todos" && isFuture(shiftPeriod(period, date, 1)));
  const delivered = done.filter((o) => o.status === "entregado");
  const amountSum = delivered.reduce((a, o) => a + (o.amount ?? 0), 0);

  const row = (o: Order) => (
    <Pressable key={o.id} testID={`biz-order-${o.number}`} onPress={() => router.push(`/biz-order/${o.id}`)} style={({ pressed }) => [s.card, { opacity: pressed ? 0.9 : 1 }]}>
      <View style={s.rowBetween}>
        <Text style={s.num}>#{num(o.number)} · {format(new Date(o.created_at), "EEE d MMM yyyy, HH:mm", { locale: es })}</Text>
        <StatusBadge status={o.status} />
      </View>
      <Text style={s.customer} numberOfLines={1}>{o.customer_name}</Text>
      <Text style={s.meta} numberOfLines={1}>{o.address}</Text>
      <IncidentBanner order={o} />
      <View style={[s.rowBetween, s.footer]}>
        <View style={s.inline}>
          <Ionicons name="bicycle-outline" size={16} color={o.courier_name ? colors.brandPrimary : colors.warning} />
          <Text style={[s.meta, { color: o.courier_name ? colors.onSurface : colors.warning }]} numberOfLines={1}>
            {o.courier_name ?? (o.open ? "Esperando que un repartidor acepte" : "Sin repartidor")}
          </Text>
        </View>
        <Text style={s.total}>{money(o.delivery_fee)}{o.distance_km != null ? ` · ${o.distance_km.toFixed(1)} km` : ""}</Text>
      </View>
    </Pressable>
  );

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.md }]}>
        <Pressable testID="biz-photo-button" accessibilityLabel="Foto del comercio" onPress={() => setPhotoOpen(true)}>
          {me.data ? <BizPhoto businessId={me.data.id} photo={me.data.photo} size={44} /> : <View style={s.logo}><Ionicons name="storefront" size={22} color={colors.onBrandPrimary} /></View>}
          <View style={s.camBadge}><Ionicons name="camera" size={11} color={colors.onBrandPrimary} /></View>
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={s.title} numberOfLines={1}>{me.data?.name ?? user?.name}</Text>
          <Text style={s.sub} numberOfLines={1}>{user?.email}</Text>
        </View>
        <Pressable testID="biz-change-password-button" accessibilityLabel="Cambiar contraseña" onPress={() => setPwOpen(true)} style={s.iconBtn}>
          <Ionicons name="key-outline" size={22} color={colors.onSurface} />
        </Pressable>
        <Pressable testID="biz-logout-button" onPress={signOut} style={s.iconBtn}>
          <Ionicons name="log-out-outline" size={24} color={colors.error} />
        </Pressable>
      </View>
      {q.isLoading ? (
        <Loading />
      ) : q.isError ? (
        <ErrorState message="No pudimos cargar tus pedidos" onRetry={() => q.refetch()} />
      ) : (
        <ScrollView
          contentContainerStyle={[s.content, { paddingBottom: insets.bottom + 110 }]}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => { q.refetch(); }} tintColor={colors.brandPrimary} />}
        >
          <Text style={s.section}>En curso ({active.length})</Text>
          {active.length === 0 && <EmptyState title="No tienes pedidos en curso" subtitle="Crea uno y lo llevará un repartidor." />}
          {active.map(row)}
          <Text style={s.section}>Historial de pedidos</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
            <Chip testID="biz-period-todos" label="Todos" selected={period === "todos"} onPress={() => setPeriod("todos")} />
            {PERIODS.map((p) => (
              <Chip key={p} testID={`biz-period-${p}`} label={PERIOD_LABEL[p]} selected={period === p} onPress={() => setPeriod(p)} />
            ))}
            <Chip testID="biz-period-rango" label="Entre fechas" selected={period === "rango"} onPress={() => setPeriod("rango")} />
          </ScrollView>
          {period === "rango" && <RangePicker testID="biz-range" value={range} onChange={setRange} />}
          {period !== "todos" && period !== "rango" && (
            <View style={s.dateRow}>
              <Pressable testID="biz-period-prev" onPress={() => setDate(shiftPeriod(period, date, -1))} style={s.iconBtn}>
                <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
              </Pressable>
              <Pressable testID="biz-open-calendar" onPress={() => setCalendar(true)} style={s.dateBtn}>
                <Ionicons name="calendar-outline" size={18} color={colors.brandPrimary} />
                <Text testID="biz-period-label" style={s.dateText} numberOfLines={1}>{periodLabel(period, date)}</Text>
              </Pressable>
              <Pressable testID="biz-period-next" disabled={nextDisabled} onPress={() => setDate(shiftPeriod(period, date, 1))} style={[s.iconBtn, nextDisabled && { opacity: 0.3 }]}>
                <Ionicons name="chevron-forward" size={22} color={colors.onSurface} />
              </Pressable>
            </View>
          )}
          {period !== "todos" && hist.isLoading ? (
            <Loading />
          ) : done.length === 0 ? (
            <Text testID="biz-history-empty" style={s.sub}>No hay pedidos terminados en estas fechas.</Text>
          ) : (
            <Text testID="biz-history-count" style={s.sub}>
              {done.length} {done.length === 1 ? "pedido" : "pedidos"} · {delivered.length} entregados · {done.length - delivered.length} cancelados · importe {money(amountSum)}
            </Text>
          )}
          {done.map(row)}
        </ScrollView>
      )}
      <ChangePasswordSheet visible={pwOpen} onClose={() => setPwOpen(false)} />
      <CalendarSheet visible={calendar} value={date} onClose={() => setCalendar(false)} onSelect={(d) => setDate(startOfDay(d))} />
      {!!me.data && (
        <ProfilePhotoSheet
          visible={photoOpen}
          onClose={() => setPhotoOpen(false)}
          userId={me.data.id}
          name={me.data.name}
          photo={me.data.photo ?? null}
          endpoint="/biz/photo"
          title="Foto de tu comercio"
          hint="Los repartidores y el administrador verán esta foto para reconocer tu comercio al recoger los pedidos."
          preview={<BizPhoto businessId={me.data.id} photo={me.data.photo} size={96} />}
          onSaved={() => qc.invalidateQueries({ queryKey: ["biz-me"] })}
        />
      )}
      <View style={[s.fab, { paddingBottom: insets.bottom + space.md }]}>
        <Button testID="biz-new-order-button" title="Nuevo pedido" icon="add" size="lg" onPress={() => router.push("/order/new")} />
      </View>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: space.md, paddingHorizontal: space.lg, paddingBottom: space.md, borderBottomWidth: 1, borderBottomColor: c.divider },
  logo: { width: 44, height: 44, borderRadius: radius.md, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: font.extrabold, fontSize: 22, color: c.onSurface, letterSpacing: -0.3 },
  sub: { fontFamily: font.medium, fontSize: 13, color: c.muted },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  content: { padding: space.lg, gap: space.md },
  section: { fontFamily: font.bold, fontSize: 18, color: c.onSurface, marginTop: space.sm },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, padding: space.lg, gap: space.xs },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: space.sm },
  inline: { flexDirection: "row", alignItems: "center", gap: 6, flexShrink: 1 },
  num: { fontFamily: font.bold, fontSize: 13, color: c.muted },
  customer: { fontFamily: font.bold, fontSize: 17, color: c.onSurface },
  meta: { fontFamily: font.medium, fontSize: 13, color: c.muted, flexShrink: 1 },
  footer: { marginTop: space.sm, paddingTop: space.sm, borderTopWidth: 1, borderTopColor: c.divider },
  total: { fontFamily: font.extrabold, fontSize: 16, color: c.onSurface, flexShrink: 0 },
  fab: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: space.lg, paddingTop: space.md, backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.divider },
  camBadge: { position: "absolute", right: -2, bottom: -2, width: 20, height: 20, borderRadius: 10, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: c.surface },
  dateRow: { flexDirection: "row", alignItems: "center", gap: space.xs },
  dateBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: space.sm, height: 44, borderRadius: radius.pill, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, paddingHorizontal: space.md },
  dateText: { fontFamily: font.bold, fontSize: 14, color: c.onSurface, flexShrink: 1 },
}));
