import { useRouter } from "expo-router";
import { formatDistanceToNowStrict, format } from "date-fns";
import { es } from "date-fns/locale";
import { Pressable, Text, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";

import { money, Order, num } from "@/src/api";
import { Elapsed } from "@/src/components/Elapsed";
import { IncidentBanner } from "@/src/components/IncidentBanner";
import { Ionicons, StatusBadge } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { deliveryMinutes, durationLabel, PAYMENT_ICON, PAYMENT_LABEL } from "@/src/status";
import { makeStyles, useTheme } from "@/src/theme";

export const ago = (iso: string) => formatDistanceToNowStrict(new Date(iso), { locale: es, addSuffix: true });

export function OrderCard({ order, index = 0 }: { order: Order; index?: number }) {
  const s = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const mins = order.status === "entregado" ? deliveryMinutes(order.history ?? []) : null;
  const toCharge = order.payment_method === "pagado" ? 0 : order.amount ?? 0;
  return (
    <Animated.View entering={FadeInDown.delay(Math.min(index, 8) * 40)}>
      <Pressable
        testID={`order-card-${order.number}`}
        onPress={() => router.push(`/order/${order.id}`)}
        style={({ pressed }) => [s.card, { opacity: pressed ? 0.9 : 1 }]}
      >
        <View style={s.row}>
          <Text style={s.num}>#{num(order.number)}</Text>
          <StatusBadge status={order.status} />
        </View>
        <Text style={s.customer} numberOfLines={1}>{order.customer_name}</Text>
        {(order.status === "nuevo" || order.status === "preparacion" || order.status === "en_camino") && (
          <View style={s.meta}>
            <Ionicons name="time-outline" size={14} color={colors.warning} />
            <Elapsed testID={`card-elapsed-${order.number}`} from={order.created_at} prefix="Desde que se creó: " style={[s.metaText, { color: colors.warning }]} />
          </View>
        )}
        {!!order.scheduled_for && (
          <View style={s.meta}>
            <Ionicons name="calendar-outline" size={14} color={colors.info} />
            <Text style={s.metaText}>Programado {format(new Date(order.scheduled_for), "EEE d MMM, HH:mm", { locale: es })}</Text>
          </View>
        )}
        <IncidentBanner order={order} />
        {mins != null && (
          <View style={s.meta}>
            <Ionicons name="stopwatch-outline" size={14} color={colors.brandPrimary} />
            <Text testID={`card-duration-${order.number}`} style={[s.metaText, s.courier]}>Entregado en {durationLabel(mins)} desde la recogida</Text>
          </View>
        )}
        <View style={s.meta}>
          <Ionicons name="storefront-outline" size={14} color={colors.muted} />
          <Text style={s.metaText} numberOfLines={1}>{order.business_name}</Text>
          <Text style={s.metaText}>·</Text>
          <Text style={s.metaText}>{ago(order.created_at)}</Text>
        </View>
        <View style={[s.row, s.footer]}>
          <View style={s.meta}>
            <Ionicons name="bicycle-outline" size={16} color={order.courier_name ? colors.brandPrimary : colors.muted} />
            <Text style={[s.metaText, order.courier_name ? s.courier : null]} numberOfLines={1}>{order.courier_name ?? "Sin repartidor"}</Text>
            {!!order.delivery_photo && <Ionicons testID={`card-photo-${order.number}`} name="camera" size={16} color={colors.brandPrimary} />}
            {!!order.delivery_note && <Ionicons testID={`card-note-${order.number}`} name="chatbubble-ellipses" size={15} color={colors.brandPrimary} />}
          </View>
          <View style={s.meta}>
            <Ionicons name={PAYMENT_ICON[order.payment_method ?? "efectivo"]} size={16} color={colors.muted} />
            <Text style={s.metaText}>{PAYMENT_LABEL[order.payment_method ?? "efectivo"]}</Text>
          </View>
        </View>
        <View style={s.amounts}>
          <View testID={`card-fee-${order.number}`} style={s.amountBox}>
            <Text style={s.amountLabel}>Envío</Text>
            <Text style={s.amountValue}>{money(order.delivery_fee)}</Text>
          </View>
          <View testID={`card-charge-${order.number}`} style={[s.amountBox, toCharge > 0 && s.amountCharge]}>
            <Text style={s.amountLabel}>{order.payment_method === "pagado" ? "Ya pagado" : "Cobrar al cliente"}</Text>
            <Text style={s.amountValue}>{order.payment_method === "pagado" ? "—" : money(toCharge)}</Text>
          </View>
        </View>
      </Pressable>
    </Animated.View>
  );
}

const useStyles = makeStyles((c) => ({
  card: {
    backgroundColor: c.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: c.border,
    padding: space.lg,
    gap: space.xs,
  },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  num: { fontFamily: font.bold, fontSize: 13, color: c.muted },
  customer: { fontFamily: font.bold, fontSize: 17, color: c.onSurface, marginTop: space.xs },
  meta: { flexDirection: "row", alignItems: "center", gap: 6, flexShrink: 1 },
  metaText: { fontFamily: font.medium, fontSize: 13, color: c.muted },
  courier: { color: c.onSurface },
  footer: { marginTop: space.sm, paddingTop: space.sm, borderTopWidth: 1, borderTopColor: c.divider },
  total: { fontFamily: font.extrabold, fontSize: 16, color: c.onSurface, marginLeft: space.sm },
  amounts: { flexDirection: "row", gap: space.sm, marginTop: space.sm },
  amountBox: { flex: 1, backgroundColor: c.surface, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, paddingVertical: space.sm, paddingHorizontal: space.md },
  amountCharge: { borderColor: c.warning },
  amountLabel: { fontFamily: font.medium, fontSize: 12, color: c.muted },
  amountValue: { fontFamily: font.extrabold, fontSize: 17, color: c.onSurface },
}));
