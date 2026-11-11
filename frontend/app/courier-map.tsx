import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Order, num } from "@/src/api";
import { useAuth } from "@/src/auth";
import { TripMap, TripPoint } from "@/src/components/TripMap";
import { Ionicons, Loading } from "@/src/components/ui";
import { font, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";
import { periodRange } from "@/src/period";

// Full-screen map with every active task of the courier: pickups, deliveries and own position.
export default function CourierMapScreen() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const q = useQuery({
    queryKey: ["courier-orders"],
    queryFn: () => api<{ active: Order[] }>(`/courier/orders?since=${encodeURIComponent(periodRange("dia", new Date())[0].toISOString())}`),
    refetchInterval: 6000,
  });
  const openQ = useQuery({ queryKey: ["courier-open"], queryFn: () => api<Order[]>("/courier/open-orders"), refetchInterval: 6000 });
  const me = useQuery({ queryKey: ["me-pos"], queryFn: () => api<{ lat?: number; lng?: number }>("/auth/me"), refetchInterval: 10000 });

  const points: TripPoint[] = [
    { id: "me", kind: "courier", lat: me.data?.lat ?? user?.lat, lng: me.data?.lng ?? user?.lng, title: "Tu ubicación" },
    ...(q.data?.active ?? []).flatMap((o): TripPoint[] => [
      ...(o.status !== "en_camino" ? [{ id: `p-${o.id}`, kind: "pickup" as const, lat: o.pickup_lat, lng: o.pickup_lng, title: `#${num(o.number)} Recoger: ${o.business_name}` }] : []),
      { id: `d-${o.id}`, kind: "dest", lat: o.dest_lat, lng: o.dest_lng, title: `#${num(o.number)} Entregar: ${o.address}` },
    ]),
    ...(openQ.data ?? []).flatMap((o): TripPoint[] => [
      { id: `op-${o.id}`, kind: "pickup", lat: o.pickup_lat, lng: o.pickup_lng, title: `POR ACEPTAR #${num(o.number)} Recoger: ${o.business_name}` },
      { id: `od-${o.id}`, kind: "dest", lat: o.dest_lat, lng: o.dest_lng, title: `POR ACEPTAR #${num(o.number)} Entregar: ${o.address}` },
    ]),
  ];

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <Pressable testID="back-button" onPress={() => router.back()} style={s.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={s.title}>Mis tareas ({q.data?.active.length ?? 0}) · por aceptar ({openQ.data?.length ?? 0})</Text>
      </View>
      {q.isLoading ? <Loading /> : <TripMap points={points} style={[s.map, { marginBottom: insets.bottom }]} big />}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: space.xs, paddingHorizontal: space.sm, paddingBottom: space.sm },
  title: { fontFamily: font.extrabold, fontSize: 17, color: c.onSurface, flexShrink: 1 },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  map: { flex: 1 },
}));
