import { createElement } from "react";
import { Linking, Pressable, StyleProp, Text, View, ViewStyle } from "react-native";

import { Ionicons, IconName } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

export type TripPoint = { id?: string; kind: "courier" | "pickup" | "dest"; lat?: number | null; lng?: number | null; title: string };

export const TRIP_ICON: Record<TripPoint["kind"], IconName> = { courier: "bicycle", pickup: "storefront", dest: "home" };
export const TRIP_LABEL: Record<TripPoint["kind"], string> = { courier: "Repartidor", pickup: "Recoger", dest: "Entregar" };

export function useTripColors() {
  const { colors } = useTheme();
  return { courier: colors.info, pickup: colors.warning, dest: colors.brandPrimary };
}

// Material icon paths drawn inside the Leaflet pins.
const SVG: Record<TripPoint["kind"], string> = {
  courier:
    "M15.5 5.5c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zM5 12c-2.8 0-5 2.2-5 5s2.2 5 5 5 5-2.2 5-5-2.2-5-5-5zm0 8.5c-1.9 0-3.5-1.6-3.5-3.5s1.6-3.5 3.5-3.5 3.5 1.6 3.5 3.5-1.6 3.5-3.5 3.5zm5.8-10l2.4-2.4.8.8c1.3 1.3 3 2.1 5.1 2.1V9c-1.5 0-2.7-.6-3.6-1.5l-1.9-1.9c-.5-.4-1-.6-1.6-.6s-1.1.2-1.4.6L7.8 8.4c-.4.4-.6.9-.6 1.4 0 .6.2 1.1.6 1.4L11 14v5h2v-6.2l-2.2-2.3zM19 12c-2.8 0-5 2.2-5 5s2.2 5 5 5 5-2.2 5-5-2.2-5-5-5zm0 8.5c-1.9 0-3.5-1.6-3.5-3.5s1.6-3.5 3.5-3.5 3.5 1.6 3.5 3.5-1.6 3.5-3.5 3.5z",
  pickup: "M20 4H4v2h16V4zm1 10v-2l-1-5H4l-1 5v2h1v6h10v-6h4v6h2v-6h1zm-9 4H6v-4h6v4z",
  dest: "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z",
};

function mapHtml(points: { lat: number; lng: number; color: string; svg: string; title: string }[]) {
  return `<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#m{margin:0;height:100%}.pin{width:34px;height:34px;border-radius:17px;border:3px solid #fff;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(0,0,0,.35)}</style>
</head><body><div id="m"></div><script>
var pts=${JSON.stringify(points)};
var m=L.map('m',{zoomControl:true});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(m);
var b=[];
pts.forEach(function(p){
  var html='<div class="pin" style="background:'+p.color+'"><svg width="18" height="18" viewBox="0 0 24 24" fill="#fff"><path d="'+p.svg+'"/></svg></div>';
  L.marker([p.lat,p.lng],{icon:L.divIcon({className:'',html:html,iconSize:[34,34],iconAnchor:[17,17]})}).addTo(m).bindPopup(p.title);
  b.push([p.lat,p.lng]);
});
function fit(){m.invalidateSize();if(b.length>1){m.fitBounds(b,{padding:[40,40],maxZoom:16});}else if(b.length){m.setView(b[0],15);}else{m.setView([40.4168,-3.7038],12);}}
fit();setTimeout(fit,300);setTimeout(fit,1200);window.addEventListener('resize',fit);if(window.ResizeObserver){new ResizeObserver(fit).observe(document.getElementById('m'));}
</script></body></html>`;
}

// Web preview: real OpenStreetMap map (Leaflet in an iframe) with an icon per point.
export function TripMap({ points, style, big }: { points: TripPoint[]; style?: StyleProp<ViewStyle>; big?: boolean }) {
  const s = useStyles();
  const tc = useTripColors();
  const pts = points
    .filter((p) => p.lat != null && p.lng != null)
    .map((p) => ({ lat: p.lat as number, lng: p.lng as number, color: tc[p.kind], svg: SVG[p.kind], title: `${TRIP_LABEL[p.kind]}: ${p.title}` }));
  return (
    <View testID="trip-map" style={big ? [s.box, style] : s.box}>
      <View style={big ? { flex: 1 } : s.frame}>
        {createElement("iframe", {
          srcDoc: mapHtml(pts),
          title: "Mapa de la ruta",
          style: { border: 0, width: "100%", height: big ? "100%" : 240, display: "block" },
        })}
      </View>
      <View style={s.legend}>
        {points.filter((p, i, a) => a.findIndex((x) => x.kind === p.kind) === i).map((p) => (
          <Pressable
            key={p.kind}
            testID={`trip-point-${p.kind}`}
            disabled={p.lat == null}
            onPress={() => Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lng}`)}
            style={s.legendItem}
          >
            <View style={[s.pin, { backgroundColor: tc[p.kind] }]}>
              <Ionicons name={TRIP_ICON[p.kind]} size={12} color="#FFFFFF" />
            </View>
            <Text style={s.legendText}>{TRIP_LABEL[p.kind]}{p.lat == null ? " (sin ubicación)" : ""}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  box: { borderRadius: radius.md, overflow: "hidden", backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  frame: { height: 240, overflow: "hidden" },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: space.md, justifyContent: "center", paddingVertical: space.sm },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 32 },
  pin: { width: 22, height: 22, borderRadius: 11, alignItems: "center", justifyContent: "center" },
  legendText: { fontFamily: font.semibold, fontSize: 12, color: c.onSurfaceTertiary },
}));
