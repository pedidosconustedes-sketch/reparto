import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Business, Dashboard, money } from "@/src/api";
import { useAuth } from "@/src/auth";
import { OrderCard } from "@/src/components/OrderCard";
import { Button, EmptyState, ErrorState, Ionicons, IconName, Loading } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { usesNativeTabs } from "@/src/navigation";
import { STATUS_LABEL, statusColor } from "@/src/status";
import { makeStyles, useTheme } from "@/src/theme";

export default function Home() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { user } = useAuth();
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/dashboard"), refetchInterval: 15000 });
  const biz = useQuery({ queryKey: ["businesses"], queryFn: () => api<Business[]>("/businesses") });
  const d = dash.data;

  const metrics: { label: string; value: string; icon: IconName; testID: string }[] = d
    ? [
        { label: "Envíos de hoy", value: money(d.revenue_today), icon: "cash-outline", testID: "metric-revenue" },
        { label: "Órdenes de hoy", value: String(d.orders_today), icon: "receipt-outline", testID: "metric-orders" },
        { label: "Repartidores en línea", value: `${d.couriers_online}/${d.couriers_total}`, icon: "bicycle-outline", testID: "metric-couriers" },
        { label: "Entregadas hoy", value: String(d.delivered_today), icon: "checkmark-done-outline", testID: "metric-delivered" },
      ]
    : [];

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.md }]}>
        <View style={{ flex: 1 }}>
          <Text style={s.hello}>Hola, {user?.name?.split(" ")[0]}</Text>
          <Text style={s.date}>Resumen de tu operación</Text>
        </View>
        <Pressable testID="header-new-order-button" onPress={() => router.push("/order/new")} style={s.addBtn}>
          <Ionicons name="add" size={24} color={colors.onBrandPrimary} />
        </Pressable>
      </View>
      {dash.isLoading ? (
        <Loading />
      ) : dash.isError ? (
        <ErrorState message="No pudimos cargar el resumen" onRetry={() => dash.refetch()} />
      ) : (
        <ScrollView
          contentContainerStyle={{ paddingBottom: bottomChrome + space.xl }}
          refreshControl={<RefreshControl refreshing={dash.isRefetching} onRefresh={() => { dash.refetch(); biz.refetch(); }} tintColor={colors.brandPrimary} />}
        >
          <Pressable testID="open-reports-button" onPress={() => router.push("/reports")} style={({ pressed }) => [s.reportsCard, { opacity: pressed ? 0.9 : 1 }]}>
            <Ionicons name="stats-chart" size={22} color={colors.onBrandPrimary} />
            <View style={{ flex: 1 }}>
              <Text style={s.reportsTitle}>Reportes y pedidos por mes</Text>
              <Text style={s.reportsSub}>Total del mes, semana o día y todos los pedidos</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.onBrandPrimary} />
          </Pressable>
          <View style={s.grid}>
            {metrics.map((m) => (
              <View key={m.label} style={s.metric}>
                <Ionicons name={m.icon} size={20} color={colors.brandPrimary} />
                <Text testID={m.testID} style={s.metricValue}>{m.value}</Text>
                <Text style={s.metricLabel}>{m.label}</Text>
              </View>
            ))}
          </View>

          <View style={s.pipeline}>
            {(["nuevo", "preparacion", "en_camino"] as const).map((st) => (
              <Pressable key={st} testID={`pipeline-${st}`} style={s.pipeItem} onPress={() => router.push({ pathname: "/orders", params: { status: st } })}>
                <View style={[s.pipeDot, { backgroundColor: statusColor(st, colors) }]} />
                <Text style={s.pipeCount}>{d?.counts[st] ?? 0}</Text>
                <Text style={s.pipeLabel} numberOfLines={1}>{STATUS_LABEL[st]}</Text>
              </Pressable>
            ))}
          </View>

          <Text style={s.section}>Tus comercios</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.bizRow}>
            {(biz.data ?? []).map((b) => (
              <Pressable key={b.id} testID={`home-business-${b.id}`} onPress={() => router.push(`/business/${b.id}`)} style={s.biz}>
                <LinearGradient colors={[colors.brandSecondary, colors.brandTertiary]} style={s.bizIcon}>
                  <Ionicons name="storefront" size={20} color={colors.onBrandSecondary} />
                </LinearGradient>
                <Text style={s.bizName} numberOfLines={1}>{b.name}</Text>
                <Text style={s.bizMeta}>{b.active_orders ?? 0} activas · {b.category}</Text>
              </Pressable>
            ))}
            <Pressable testID="home-add-business" onPress={() => router.push("/manage")} style={[s.biz, s.bizAdd]}>
              <Ionicons name="add-circle-outline" size={28} color={colors.brandPrimary} />
              <Text style={s.bizMeta}>Agregar</Text>
            </Pressable>
          </ScrollView>

          <Text style={s.section}>Órdenes activas</Text>
          <View style={s.list}>
            {d && d.recent.length === 0 ? (
              <EmptyState
                testID="home-empty"
                title="No hay órdenes activas"
                subtitle="Crea una orden cuando entre un pedido."
                action={<Button testID="home-create-order" title="Crear orden" icon="add" onPress={() => router.push("/order/new")} />}
              />
            ) : (
              d?.recent.map((o, i) => <OrderCard key={o.id} order={o} index={i} />)
            )}
          </View>
        </ScrollView>
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: space.lg, paddingBottom: space.md, backgroundColor: c.surface },
  hello: { fontFamily: font.extrabold, fontSize: 26, color: c.onSurface, letterSpacing: -0.5 },
  date: { fontFamily: font.medium, fontSize: 14, color: c.muted },
  addBtn: { width: 48, height: 48, borderRadius: 24, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: space.md, paddingHorizontal: space.lg },
  reportsCard: { flexDirection: "row", alignItems: "center", gap: space.md, marginHorizontal: space.lg, marginBottom: space.md, backgroundColor: c.brandPrimary, borderRadius: radius.md, padding: space.lg, minHeight: 64 },
  reportsTitle: { fontFamily: font.bold, fontSize: 15, color: c.onBrandPrimary },
  reportsSub: { fontFamily: font.medium, fontSize: 12, color: c.onBrandPrimary, opacity: 0.85 },
  metric: { flexBasis: "47%", flexGrow: 1, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, padding: space.lg, gap: space.xs },
  metricValue: { fontFamily: font.extrabold, fontSize: 24, color: c.onSurface, marginTop: space.sm },
  metricLabel: { fontFamily: font.medium, fontSize: 12, color: c.muted },
  pipeline: { flexDirection: "row", marginHorizontal: space.lg, marginTop: space.md, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border },
  pipeItem: { flex: 1, padding: space.md, alignItems: "flex-start", gap: 2 },
  pipeDot: { width: 8, height: 8, borderRadius: 4 },
  pipeCount: { fontFamily: font.extrabold, fontSize: 20, color: c.onSurface },
  pipeLabel: { fontFamily: font.medium, fontSize: 12, color: c.muted },
  section: { fontFamily: font.bold, fontSize: 18, color: c.onSurface, paddingHorizontal: space.lg, marginTop: space.xl, marginBottom: space.md },
  bizRow: { gap: space.md, paddingHorizontal: space.lg },
  biz: { width: 150, flexShrink: 0, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, padding: space.md, gap: space.xs },
  bizAdd: { width: 100, alignItems: "center", justifyContent: "center", borderStyle: "dashed" },
  bizIcon: { width: 40, height: 40, borderRadius: radius.md, alignItems: "center", justifyContent: "center", marginBottom: space.xs },
  bizName: { fontFamily: font.bold, fontSize: 14, color: c.onSurface },
  bizMeta: { fontFamily: font.medium, fontSize: 12, color: c.muted },
  list: { paddingHorizontal: space.lg, gap: space.md },
}));
