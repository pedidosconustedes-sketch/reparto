import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Linking, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Order, User, num } from "@/src/api";
import { Avatar } from "@/src/components/Avatar";
import { ago } from "@/src/components/OrderCard";
import { TripMap, TripPoint } from "@/src/components/TripMap";
import { ErrorState, Ionicons, Loading } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme } from "@/src/theme";

// Control tower: every courier's live position plus every active order (pickup + delivery) on one map.
export default function MapScreen() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const [focus, setFocus] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["couriers"], queryFn: () => api<User[]>("/couriers"), refetchInterval: 10000 });
  const oq = useQuery({ queryKey: ["orders", "active-map"], queryFn: () => api<Order[]>("/orders?active=true"), refetchInterval: 10000 });

  const couriers = q.data ?? [];
  const orders = (oq.data ?? []).filter((o) => focus === null || (focus === "none" ? !o.courier_id : o.courier_id === focus));
  const points: TripPoint[] = [
    ...couriers
      .filter((c) => focus === null || c.id === focus)
      .map((c): TripPoint => ({ id: `c-${c.id}`, kind: "courier", lat: c.lat, lng: c.lng, title: `${c.name} · ${c.online ? "En línea" : "Desconectado"}` })),
    ...orders.flatMap((o): TripPoint[] => {
      const who = o.courier_name ?? (o.open ? "LIBRE (sin aceptar)" : "SIN REPARTIDOR");
      return [
        ...(o.status !== "en_camino" ? [{ id: `p-${o.id}`, kind: "pickup" as const, lat: o.pickup_lat, lng: o.pickup_lng, title: `#${num(o.number)} Recoger en ${o.business_name} · ${who}` }] : []),
        { id: `d-${o.id}`, kind: "dest", lat: o.dest_lat, lng: o.dest_lng, title: `#${num(o.number)} Entregar en ${o.address} · ${who}` },
      ];
    }),
  ];
  const unassigned = (oq.data ?? []).filter((o) => !o.courier_id).length;

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.md }]}>
        <Text style={s.title}>Torre de control</Text>
        <Text style={s.sub}>
          {(oq.data ?? []).length} pedidos activos · {couriers.filter((c) => c.online).length} repartidores en línea · se actualiza cada 10 s
        </Text>
      </View>
      {q.isLoading || oq.isLoading ? (
        <Loading />
      ) : q.isError || oq.isError ? (
        <ErrorState message="No pudimos cargar el mapa" onRetry={() => { q.refetch(); oq.refetch(); }} />
      ) : (
        <>
          <View testID="control-tower-map" style={s.map}>
            <TripMap key={focus ?? "all"} big style={{ flex: 1 }} points={points} />
          </View>
          <View style={[s.tray, { paddingBottom: bottomChrome + space.md }]}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.trayRow}>
              <Pressable testID="map-filter-all" onPress={() => setFocus(null)} style={[s.card, s.smallCard, focus === null && { borderColor: colors.brandPrimary }]}>
                <Ionicons name="layers-outline" size={22} color={colors.brandPrimary} />
                <Text style={s.name}>Todos</Text>
                <Text style={s.meta}>{(oq.data ?? []).length} pedidos</Text>
              </Pressable>
              {unassigned > 0 && (
                <Pressable testID="map-filter-none" onPress={() => setFocus(focus === "none" ? null : "none")} style={[s.card, s.smallCard, focus === "none" && { borderColor: colors.warning }]}>
                  <Ionicons name="alert-circle-outline" size={22} color={colors.warning} />
                  <Text style={s.name}>Sin repartidor</Text>
                  <Text style={s.meta}>{unassigned} pedidos</Text>
                </Pressable>
              )}
              {couriers.map((c) => {
                const mine = (oq.data ?? []).filter((o) => o.courier_id === c.id);
                return (
                  <Pressable
                    key={c.id}
                    testID={`map-courier-${c.id}`}
                    onPress={() => setFocus(focus === c.id ? null : c.id)}
                    style={[s.card, focus === c.id && { borderColor: colors.brandPrimary }]}
                  >
                    <View style={s.cardTop}>
                      <Avatar userId={c.id} name={c.name} hasPhoto={!!c.profile_photo} version={c.profile_photo} size={32} />
                      <View style={{ flex: 1 }}>
                        <Text style={s.name} numberOfLines={1}>{c.name}</Text>
                        <View style={s.cardTop}>
                          <View style={[s.dot, { backgroundColor: c.online ? colors.success : colors.muted }]} />
                          <Text style={s.meta}>{c.online ? "En línea" : "Desconectado"}</Text>
                        </View>
                      </View>
                    </View>
                    <Text style={s.meta} numberOfLines={2}>
                      {mine.length ? mine.map((o) => `#${num(o.number)}`).join(", ") : "Sin pedidos"}
                    </Text>
                    <Text style={s.meta}>{c.location_at ? `Ubicación ${ago(c.location_at)}` : "Sin ubicación"}</Text>
                    {!!c.phone && (
                      <Pressable testID={`map-call-${c.id}`} onPress={() => Linking.openURL(`tel:${c.phone}`)} style={s.call}>
                        <Ionicons name="call" size={14} color={colors.onBrandSecondary} />
                        <Text style={s.callText}>Llamar</Text>
                      </Pressable>
                    )}
                  </Pressable>
                );
              })}
              {couriers.length === 0 && <Text style={s.meta}>Agrega repartidores en Gestión.</Text>}
            </ScrollView>
          </View>
        </>
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: space.lg, paddingBottom: space.md },
  title: { fontFamily: font.extrabold, fontSize: 26, color: c.onSurface, letterSpacing: -0.5 },
  sub: { fontFamily: font.medium, fontSize: 13, color: c.muted },
  map: { flex: 1 },
  tray: { backgroundColor: c.surface, paddingTop: space.md, borderTopWidth: 1, borderTopColor: c.divider },
  trayRow: { gap: space.md, paddingHorizontal: space.lg },
  card: { width: 200, flexShrink: 0, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1.5, borderColor: c.border, padding: space.md, gap: 4 },
  smallCard: { width: 120, justifyContent: "center" },
  cardTop: { flexDirection: "row", alignItems: "center", gap: space.sm },
  dot: { width: 8, height: 8, borderRadius: 4 },
  name: { fontFamily: font.bold, fontSize: 15, color: c.onSurface },
  meta: { fontFamily: font.medium, fontSize: 12, color: c.muted },
  call: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", marginTop: space.xs, backgroundColor: c.brandSecondary, paddingHorizontal: space.md, height: 32, borderRadius: radius.pill },
  callText: { fontFamily: font.bold, fontSize: 12, color: c.onBrandSecondary },
}));
