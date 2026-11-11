import { Linking, Platform, Pressable, Text } from "react-native";

import { Ionicons, IconName, Sheet } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

export type NavTarget = { address: string; lat?: number | null; lng?: number | null };

function links(t: NavTarget) {
  const q = encodeURIComponent(t.address);
  const hasLL = t.lat != null && t.lng != null;
  const ll = hasLL ? `${t.lat},${t.lng}` : "";
  const out: { key: string; label: string; icon: IconName; url: string }[] = [
    { key: "google", label: "Google Maps", icon: "logo-google", url: `https://www.google.com/maps/dir/?api=1&destination=${hasLL ? ll : q}&travelmode=driving` },
    { key: "waze", label: "Waze", icon: "car-sport", url: hasLL ? `https://waze.com/ul?ll=${ll}&navigate=yes` : `https://waze.com/ul?q=${q}&navigate=yes` },
  ];
  if (Platform.OS === "ios") out.push({ key: "apple", label: "Apple Maps", icon: "map", url: `maps://?daddr=${hasLL ? ll : q}` });
  return out;
}

export function NavSheet({ target, onClose }: { target: NavTarget | null; onClose: () => void }) {
  const s = useStyles();
  const { colors } = useTheme();
  return (
    <Sheet testID="nav-sheet" visible={!!target} onClose={onClose} title="Abrir con">
      {!!target && <Text style={s.addr}>{target.address}</Text>}
      {target &&
        links(target).map((l) => (
          <Pressable
            key={l.key}
            testID={`nav-app-${l.key}`}
            onPress={() => {
              Linking.openURL(l.url);
              onClose();
            }}
            style={s.row}
          >
            <Ionicons name={l.icon} size={22} color={colors.brandPrimary} />
            <Text style={s.label}>{l.label}</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.muted} />
          </Pressable>
        ))}
    </Sheet>
  );
}

const useStyles = makeStyles((c) => ({
  addr: { fontFamily: font.semibold, fontSize: 14, color: c.muted },
  row: { flexDirection: "row", alignItems: "center", gap: space.md, minHeight: 56, paddingHorizontal: space.md, borderRadius: radius.md, borderWidth: 1, borderColor: c.border },
  label: { flex: 1, fontFamily: font.bold, fontSize: 16, color: c.onSurface },
}));
