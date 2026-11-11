import { format } from "date-fns";
import { Text, View } from "react-native";

import { Order } from "@/src/api";
import { Ionicons } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

// Latest courier incident, shown on order cards so it is visible without opening the order.
export function IncidentBanner({ order }: { order: Order }) {
  const s = useStyles();
  const { colors } = useTheme();
  const list = order.incidents ?? [];
  if (!list.length) return null;
  const inc = list[list.length - 1];
  return (
    <View testID={`incident-banner-${order.number}`} style={s.box}>
      <Ionicons name="warning" size={18} color={colors.error} />
      <View style={{ flex: 1 }}>
        <Text style={s.title} numberOfLines={1}>
          {inc.label}{list.length > 1 ? ` (+${list.length - 1})` : ""}
        </Text>
        <Text style={s.text} numberOfLines={2}>
          {format(new Date(inc.at), "HH:mm")} · {inc.by}{inc.note ? `: ${inc.note}` : ""}
        </Text>
      </View>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  box: { flexDirection: "row", alignItems: "flex-start", gap: space.sm, marginTop: space.xs, padding: space.sm, borderRadius: radius.md, borderWidth: 1, borderColor: c.error, backgroundColor: c.surface },
  title: { fontFamily: font.bold, fontSize: 14, color: c.error },
  text: { fontFamily: font.medium, fontSize: 13, color: c.onSurface },
}));
