import { useRef } from "react";
import { StyleProp, Text, View, ViewStyle } from "react-native";
import MapView, { Marker } from "react-native-maps";

import { Ionicons, IconName } from "@/src/components/ui";
import { font, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

export type TripPoint = { id?: string; kind: "courier" | "pickup" | "dest"; lat?: number | null; lng?: number | null; title: string };

export const TRIP_ICON: Record<TripPoint["kind"], IconName> = { courier: "bicycle", pickup: "storefront", dest: "home" };
export const TRIP_LABEL: Record<TripPoint["kind"], string> = { courier: "Repartidor", pickup: "Recoger", dest: "Entregar" };

export function useTripColors() {
  const { colors } = useTheme();
  return { courier: colors.info, pickup: colors.warning, dest: colors.brandPrimary };
}

export function TripLegend() {
  const s = useStyles();
  const tc = useTripColors();
  return (
    <View style={s.legend}>
      {(["courier", "pickup", "dest"] as const).map((k) => (
        <View key={k} style={s.legendItem}>
          <View style={[s.legendDot, { backgroundColor: tc[k] }]}>
            <Ionicons name={TRIP_ICON[k]} size={10} color="#FFFFFF" />
          </View>
          <Text style={s.legendText}>{TRIP_LABEL[k]}</Text>
        </View>
      ))}
    </View>
  );
}

export function TripMap({ points, style }: { points: TripPoint[]; style?: StyleProp<ViewStyle>; big?: boolean }) {
  const s = useStyles();
  const tc = useTripColors();
  const ref = useRef<MapView>(null);
  const pts = points.filter((p) => p.lat != null && p.lng != null);
  const coords = pts.map((p) => ({ latitude: p.lat as number, longitude: p.lng as number }));
  const first = coords[0] ?? { latitude: 40.4168, longitude: -3.7038 };
  return (
    <View style={style}>
      <MapView
        ref={ref}
        testID="trip-map"
        style={{ flex: 1 }}
        initialRegion={{ ...first, latitudeDelta: 0.04, longitudeDelta: 0.04 }}
        onMapReady={() => {
          if (coords.length > 1) ref.current?.fitToCoordinates(coords, { edgePadding: { top: 50, right: 50, bottom: 50, left: 50 }, animated: false });
        }}
      >
        {pts.map((p) => (
          <Marker key={p.id ?? p.kind} coordinate={{ latitude: p.lat as number, longitude: p.lng as number }} title={p.title} description={TRIP_LABEL[p.kind]}>
            <View style={[s.pin, { backgroundColor: tc[p.kind] }]}>
              <Ionicons name={TRIP_ICON[p.kind]} size={18} color="#FFFFFF" />
            </View>
          </Marker>
        ))}
      </MapView>
      <TripLegend />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  pin: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", borderWidth: 3, borderColor: "#FFFFFF" },
  legend: { flexDirection: "row", gap: space.md, paddingVertical: space.sm, justifyContent: "center", backgroundColor: c.surfaceSecondary },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendDot: { width: 18, height: 18, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  legendText: { fontFamily: font.semibold, fontSize: 12, color: c.onSurfaceTertiary },
}));
