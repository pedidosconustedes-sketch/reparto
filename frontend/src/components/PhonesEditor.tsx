import { Pressable, Text, View } from "react-native";

import { Button, Field, Ionicons } from "@/src/components/ui";
import { font, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

export type NamedPhone = { name: string; phone: string };

// Editable list of phone numbers, each with the name of the person who answers it.
export function PhonesEditor({ value, onChange, testID = "phones" }: { value: NamedPhone[]; onChange: (v: NamedPhone[]) => void; testID?: string }) {
  const s = useStyles();
  const { colors } = useTheme();
  const set = (i: number, k: keyof NamedPhone, t: string) => onChange(value.map((p, j) => (j === i ? { ...p, [k]: t } : p)));
  return (
    <View style={{ gap: space.sm }}>
      {value.map((p, i) => (
        <View key={i} style={s.row}>
          <View style={{ flex: 1 }}>
            <Field testID={`${testID}-name-${i}`} label="Nombre" value={p.name} onChangeText={(t) => set(i, "name", t)} placeholder="Ej. Ana (dueña)" />
          </View>
          <View style={{ flex: 1 }}>
            <Field testID={`${testID}-phone-${i}`} label="Teléfono" value={p.phone} onChangeText={(t) => set(i, "phone", t)} keyboardType="phone-pad" />
          </View>
          <Pressable testID={`${testID}-remove-${i}`} accessibilityLabel="Quitar teléfono" onPress={() => onChange(value.filter((_, j) => j !== i))} style={s.del}>
            <Ionicons name="trash-outline" size={20} color={colors.error} />
          </Pressable>
        </View>
      ))}
      {value.length === 0 && <Text style={s.empty}>Sin teléfonos todavía.</Text>}
      {value.length < 10 && (
        <Button testID={`${testID}-add`} title="Añadir teléfono" icon="add" variant="ghost" onPress={() => onChange([...value, { name: "", phone: "" }])} />
      )}
    </View>
  );
}

export const phoneLabel = (p: NamedPhone) => (p.name ? `${p.name} · ${p.phone}` : p.phone);

const useStyles = makeStyles((c) => ({
  row: { flexDirection: "row", alignItems: "flex-end", gap: space.sm },
  del: { width: 44, height: 48, alignItems: "center", justifyContent: "center" },
  empty: { fontFamily: font.medium, fontSize: 13, color: c.muted },
}));
