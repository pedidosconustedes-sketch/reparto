import { format, startOfDay } from "date-fns";
import { es } from "date-fns/locale";
import { useState } from "react";
import { Pressable, Text, View } from "react-native";

import { CalendarSheet } from "@/src/components/CalendarSheet";
import { Ionicons } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

export type DateRange = { from: Date; to: Date };

// "Desde" / "Hasta" buttons: pick any start date and any end date.
export function RangePicker({ value, onChange, testID = "range" }: { value: DateRange; onChange: (r: DateRange) => void; testID?: string }) {
  const s = useStyles();
  const { colors } = useTheme();
  const [open, setOpen] = useState<"from" | "to" | null>(null);
  const btn = (k: "from" | "to", label: string) => (
    <Pressable testID={`${testID}-${k}`} onPress={() => setOpen(k)} style={s.btn}>
      <Ionicons name="calendar-outline" size={18} color={colors.brandPrimary} />
      <View style={{ flexShrink: 1 }}>
        <Text style={s.label}>{label}</Text>
        <Text testID={`${testID}-${k}-label`} style={s.date} numberOfLines={1}>{format(value[k], "d MMM yyyy", { locale: es })}</Text>
      </View>
    </Pressable>
  );
  return (
    <View style={s.row}>
      {btn("from", "Desde")}
      {btn("to", "Hasta")}
      <CalendarSheet
        visible={open !== null}
        value={open === "to" ? value.to : value.from}
        onClose={() => setOpen(null)}
        onSelect={(d) => {
          const day = startOfDay(d);
          if (open === "from") onChange({ from: day, to: day > value.to ? day : value.to });
          else onChange({ from: day < value.from ? day : value.from, to: day });
          setOpen(null);
        }}
      />
    </View>
  );
}

/** ISO bounds for the API: [from 00:00, day after `to` 00:00). */
export function rangeIso(r: DateRange): [string, string] {
  const [a, b] = rangeDates(r);
  return [a.toISOString(), b.toISOString()];
}

export function rangeDates(r: DateRange): [Date, Date] {
  const end = new Date(r.to);
  end.setDate(end.getDate() + 1);
  return [r.from, end];
}

export const todayRange = (): DateRange => {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return { from: d, to: d };
};

const useStyles = makeStyles((c) => ({
  row: { flexDirection: "row", gap: space.sm },
  btn: { flex: 1, flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 52, paddingHorizontal: space.md, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary },
  label: { fontFamily: font.medium, fontSize: 11, color: c.muted },
  date: { fontFamily: font.bold, fontSize: 14, color: c.onSurface },
}));
