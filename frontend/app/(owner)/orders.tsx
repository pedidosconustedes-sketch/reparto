import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { FlatList, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Dashboard, money, Order, OrderStatus } from "@/src/api";
import { OrderCard } from "@/src/components/OrderCard";
import { DateRange, RangePicker, rangeIso } from "@/src/components/RangePicker";
import { startOfDay } from "date-fns";
import { Chip, EmptyState, ErrorState, Ionicons, Loading } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { usesNativeTabs } from "@/src/navigation";
import { STATUS_LABEL } from "@/src/status";
import { makeStyles, useTheme } from "@/src/theme";

const FILTERS: (OrderStatus | "todos")[] = ["todos", "nuevo", "preparacion", "en_camino", "entregado", "cancelado"];

export default function Orders() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const params = useLocalSearchParams<{ status?: OrderStatus }>();
  const [filter, setFilter] = useState<OrderStatus | "todos">(params.status ?? "todos");
  useEffect(() => {
    if (params.status) setFilter(params.status);
  }, [params.status]);

  const [useRange, setUseRange] = useState(false);
  const [range, setRange] = useState<DateRange>(() => ({ from: startOfDay(new Date()), to: startOfDay(new Date()) }));
  const [rs, re] = rangeIso(range);
  const q = useQuery({
    queryKey: ["orders", filter, useRange ? rs : "", useRange ? re : ""],
    queryFn: () => {
      const p = new URLSearchParams();
      if (filter !== "todos") p.set("status", filter);
      if (useRange) { p.set("start", rs); p.set("end", re); }
      const qs = p.toString();
      return api<Order[]>(`/orders${qs ? `?${qs}` : ""}`);
    },
    refetchInterval: 15000,
  });
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/dashboard") });
  const list = q.data ?? [];
  const delivered = list.filter((o) => o.status === "entregado");
  const cancelled = list.filter((o) => o.status === "cancelado").length;
  const fees = delivered.reduce((a, o) => a + o.delivery_fee, 0);
  const collected = delivered.reduce((a, o) => a + (o.payment_method === "pagado" ? 0 : o.amount ?? 0), 0);

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.md }]}>
        <View style={s.titleRow}>
          <Text style={s.title}>Órdenes</Text>
          <Pressable testID="orders-range-toggle" onPress={() => setUseRange(!useRange)} style={[s.rangeToggle, useRange && { backgroundColor: colors.brandPrimary }]}>
            <Ionicons name="calendar" size={16} color={useRange ? colors.onBrandPrimary : colors.brandPrimary} />
            <Text style={[s.rangeToggleText, useRange && { color: colors.onBrandPrimary }]}>{useRange ? "Entre fechas" : "Elegir fechas"}</Text>
          </Pressable>
        </View>
        {useRange && (
          <View style={{ gap: space.sm, marginTop: space.sm, paddingHorizontal: space.lg }}>
            <RangePicker testID="orders-range" value={range} onChange={setRange} />
            <Text testID="orders-range-summary" style={[s.summary, { paddingHorizontal: 0 }]}>
              {list.length} {list.length === 1 ? "pedido" : "pedidos"} · {delivered.length} {delivered.length === 1 ? "entregado" : "entregados"} · {cancelled} {cancelled === 1 ? "cancelado" : "cancelados"} · envíos {money(fees)} · cobrado a clientes {money(collected)}
            </Text>
          </View>
        )}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipRow} contentContainerStyle={s.chips}>
          {FILTERS.map((f) => (
            <Chip
              key={f}
              testID={`filter-chip-${f}`}
              label={f === "todos" ? "Todos" : STATUS_LABEL[f]}
              selected={filter === f}
              count={!useRange && f !== "todos" && f !== "entregado" && f !== "cancelado" ? dash.data?.counts[f] : undefined}
              onPress={() => setFilter(f)}
            />
          ))}
        </ScrollView>
      </View>
      {q.isLoading ? (
        <Loading />
      ) : q.isError ? (
        <ErrorState message="No pudimos cargar las órdenes" onRetry={() => q.refetch()} />
      ) : (
        <FlatList
          testID="orders-list"
          data={q.data}
          keyExtractor={(o) => o.id}
          renderItem={({ item, index }) => <OrderCard order={item} index={index} />}
          contentContainerStyle={[s.list, { paddingBottom: bottomChrome + 96 }]}
          ItemSeparatorComponent={() => <View style={{ height: space.md }} />}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => { q.refetch(); }} tintColor={colors.brandPrimary} />}
          ListEmptyComponent={<EmptyState testID="orders-empty" title="No hay órdenes en este estado." />}
        />
      )}
      <Pressable
        testID="fab-new-order"
        onPress={() => router.push("/order/new")}
        style={({ pressed }) => [s.fab, { bottom: bottomChrome + space.lg, transform: [{ scale: pressed ? 0.96 : 1 }] }]}
      >
        <Ionicons name="add" size={22} color={colors.onBrandPrimary} />
        <Text style={s.fabText}>Nueva orden</Text>
      </Pressable>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: font.extrabold, fontSize: 26, color: c.onSurface, letterSpacing: -0.5 },
  titleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: space.lg, gap: space.sm },
  rangeToggle: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 44, paddingHorizontal: space.md, borderRadius: radius.pill, borderWidth: 1, borderColor: c.brandPrimary },
  rangeToggleText: { fontFamily: font.bold, fontSize: 13, color: c.brandPrimary },
  summary: { fontFamily: font.semibold, fontSize: 13, color: c.onSurfaceTertiary, paddingHorizontal: space.lg },
  chipRow: { height: 56, flexGrow: 0 },
  chips: { gap: space.sm, paddingHorizontal: space.lg, alignItems: "center" },
  list: { padding: space.lg },
  fab: {
    position: "absolute",
    right: space.lg,
    height: 56,
    paddingHorizontal: space.xl,
    borderRadius: radius.pill,
    backgroundColor: c.brandPrimary,
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    shadowColor: c.onSurface,
    shadowOpacity: 0.18,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  fabText: { fontFamily: font.bold, fontSize: 15, color: c.onBrandPrimary },
}));
