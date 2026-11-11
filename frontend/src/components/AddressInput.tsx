import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";

import { api } from "@/src/api";
import { Field, Ionicons } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

export type PickedAddress = { address: string; lat: number; lng: number; exact?: boolean };
type Suggestion = { id: string; description: string; source: "google" | "osm"; lat?: number; lng?: number; exact?: boolean };

type Props = {
  testID?: string;
  label: string;
  value: string;
  placeholder?: string;
  near?: { lat?: number | null; lng?: number | null } | null;
  onChangeText: (t: string) => void; // typing: coordinates are no longer exact
  onPick: (p: PickedAddress) => void; // a real address chosen from the list
  picked?: boolean;
};

const newSession = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;

// Address field with a dropdown of real addresses (Google Maps when configured, else OpenStreetMap).
export function AddressInput({ testID = "address", label, value, placeholder, near, onChangeText, onPick, picked }: Props) {
  const s = useStyles();
  const { colors } = useTheme();
  const [items, setItems] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState(false);
  const [typed, setTyped] = useState(false);
  const [exact, setExact] = useState(true);
  const session = useRef(newSession());
  const reqId = useRef(0);

  useEffect(() => {
    if (!typed || value.trim().length < 3) {
      setItems([]);
      return;
    }
    const id = ++reqId.current;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const nearQ = near?.lat != null && near?.lng != null ? `&lat=${near.lat}&lng=${near.lng}` : "";
        const r = await api<{ suggestions: Suggestion[] }>(`/places/autocomplete?q=${encodeURIComponent(value.trim())}&session=${session.current}${nearQ}`);
        if (id === reqId.current) setItems(r.suggestions);
      } catch {
        if (id === reqId.current) setItems([]);
      } finally {
        if (id === reqId.current) setLoading(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [value, typed, near?.lat, near?.lng]);

  const choose = async (sug: Suggestion) => {
    setItems([]);
    setTyped(false);
    reqId.current++;
    try {
      if (sug.source === "google") {
        const d = await api<PickedAddress>(`/places/details?place_id=${encodeURIComponent(sug.id)}&session=${session.current}`);
        onPick({ address: d.address || sug.description, lat: d.lat, lng: d.lng, exact: true });
        setExact(true);
      } else if (sug.lat != null && sug.lng != null) {
        onPick({ address: sug.description, lat: sug.lat, lng: sug.lng, exact: sug.exact !== false });
        setExact(sug.exact !== false);
      } else {
        onChangeText(sug.description);
      }
    } catch {
      onChangeText(sug.description);
    }
    session.current = newSession();
  };

  const show = focused || items.length > 0;
  return (
    <View style={s.wrap}>
      <Field
        testID={`${testID}-input`}
        label={label}
        value={value}
        placeholder={placeholder ?? "Calle y número o código postal"}
        autoCorrect={false}
        onFocus={() => setFocused(true)}
        onBlur={() => setTimeout(() => setFocused(false), 250)}
        onChangeText={(t) => {
          setTyped(true);
          onChangeText(t);
        }}
      />
      {picked && !typed && exact && (
        <View testID={`${testID}-verified`} style={s.ok}>
          <Ionicons name="checkmark-circle" size={16} color={colors.success} />
          <Text style={s.okText}>Dirección exacta en el mapa</Text>
        </View>
      )}
      {picked && !typed && !exact && (
        <View testID={`${testID}-approx`} style={s.ok}>
          <Ionicons name="alert-circle" size={16} color={colors.warning} />
          <Text style={[s.okText, { color: colors.warning }]}>Sin número de portal: el punto del mapa es aproximado. Escribe el número o añádelo en Notas.</Text>
        </View>
      )}
      {!picked && typed && value.trim().length >= 3 && items.length === 0 && !loading && show && (
        <Text style={s.hint}>Sin sugerencias: revisa la calle o añade el número y la ciudad.</Text>
      )}
      {loading && <ActivityIndicator style={{ alignSelf: "flex-start" }} color={colors.brandPrimary} />}
      {items.length > 0 && (
        <View testID={`${testID}-suggestions`} style={s.list}>
          {items.map((it, i) => (
            <Pressable
              key={`${it.id}-${i}`}
              testID={`${testID}-suggestion-${i}`}
              onPress={() => choose(it)}
              style={({ pressed }) => [s.row, i > 0 && s.rowBorder, pressed && { backgroundColor: colors.brandTertiary }]}
            >
              <Ionicons name="location-outline" size={18} color={colors.brandPrimary} />
              <Text style={s.rowText} numberOfLines={2}>{it.description}</Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  wrap: { gap: space.xs },
  list: { borderWidth: 1, borderColor: c.border, borderRadius: radius.md, backgroundColor: c.surface, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingHorizontal: space.md, minHeight: 48, paddingVertical: space.sm },
  rowBorder: { borderTopWidth: 1, borderTopColor: c.divider },
  rowText: { flex: 1, fontFamily: font.medium, fontSize: 14, color: c.onSurface },
  ok: { flexDirection: "row", alignItems: "center", gap: 6 },
  okText: { fontFamily: font.semibold, fontSize: 12, color: c.success, flexShrink: 1 },
  hint: { fontFamily: font.medium, fontSize: 12, color: c.muted },
}));
