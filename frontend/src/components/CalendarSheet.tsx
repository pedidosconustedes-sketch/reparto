import { addMonths, format, isSameDay, startOfMonth } from "date-fns";
import { es } from "date-fns/locale";
import { useEffect, useState } from "react";
import { Pressable, Text, View } from "react-native";

import { cap } from "@/src/api";
import { Ionicons, Sheet } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { isFuture } from "@/src/period";
import { makeStyles, useTheme } from "@/src/theme";

const WEEKDAYS = ["L", "M", "X", "J", "V", "S", "D"];

type Props = { visible: boolean; value: Date; onClose: () => void; onSelect: (d: Date) => void; allowFuture?: boolean };

export function CalendarSheet({ visible, value, onClose, onSelect, allowFuture }: Props) {
  const s = useStyles();
  const { colors } = useTheme();
  const [month, setMonth] = useState(startOfMonth(value));
  useEffect(() => {
    if (visible) setMonth(startOfMonth(value));
  }, [visible, value]);

  const offset = (month.getDay() + 6) % 7; // Monday first
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells: (Date | null)[] = [
    ...Array.from({ length: offset }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(month.getFullYear(), month.getMonth(), i + 1)),
  ];
  const nextDisabled = !allowFuture && isFuture(addMonths(month, 1));
  const today = new Date();

  return (
    <Sheet testID="calendar-sheet" visible={visible} onClose={onClose} title="Elegir fecha">
      <View style={s.head}>
        <Pressable testID="calendar-prev-month" onPress={() => setMonth(addMonths(month, -1))} style={s.nav}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text testID="calendar-month-label" style={s.month}>{cap(format(month, "MMMM yyyy", { locale: es }))}</Text>
        <Pressable testID="calendar-next-month" disabled={nextDisabled} onPress={() => setMonth(addMonths(month, 1))} style={[s.nav, nextDisabled && { opacity: 0.3 }]}>
          <Ionicons name="chevron-forward" size={22} color={colors.onSurface} />
        </Pressable>
      </View>
      <View style={s.grid}>
        {WEEKDAYS.map((w) => (
          <Text key={w} style={[s.cell, s.weekday]}>{w}</Text>
        ))}
        {cells.map((d, i) => {
          if (!d) return <View key={`e${i}`} style={s.cell} />;
          const disabled = allowFuture ? d.getTime() < new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() : isFuture(d);
          const selected = isSameDay(d, value);
          const isToday = isSameDay(d, today);
          return (
            <Pressable
              key={d.getDate()}
              testID={`calendar-day-${d.getDate()}`}
              disabled={disabled}
              onPress={() => {
                onSelect(d);
                onClose();
              }}
              style={s.cell}
            >
              <View style={[s.day, selected && { backgroundColor: colors.brandPrimary }, !selected && isToday && { borderWidth: 1.5, borderColor: colors.brandPrimary }]}>
                <Text style={[s.dayText, selected && { color: colors.onBrandPrimary }, disabled && { color: colors.borderStrong }]}>{d.getDate()}</Text>
              </View>
            </Pressable>
          );
        })}
      </View>
      <Pressable
        testID="calendar-today-button"
        onPress={() => {
          onSelect(today);
          onClose();
        }}
        style={s.todayBtn}
      >
        <Text style={s.todayText}>Ir a hoy</Text>
      </Pressable>
    </Sheet>
  );
}

const useStyles = makeStyles((c) => ({
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  nav: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  month: { fontFamily: font.bold, fontSize: 17, color: c.onSurface },
  grid: { flexDirection: "row", flexWrap: "wrap" },
  cell: { width: `${100 / 7}%`, height: 46, alignItems: "center", justifyContent: "center" },
  weekday: { fontFamily: font.semibold, fontSize: 12, color: c.muted, textAlign: "center", lineHeight: 46 },
  day: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  dayText: { fontFamily: font.semibold, fontSize: 15, color: c.onSurface },
  todayBtn: { alignSelf: "center", height: 44, justifyContent: "center", paddingHorizontal: space.lg, borderRadius: radius.pill },
  todayText: { fontFamily: font.bold, fontSize: 14, color: c.brandPrimary },
}));
