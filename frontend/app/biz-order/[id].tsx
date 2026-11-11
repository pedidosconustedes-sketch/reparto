import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { Linking, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, CourierCard, money, Order, OrderStatus, num } from "@/src/api";
import { Avatar } from "@/src/components/Avatar";
import { DeliveryPhoto } from "@/src/components/DeliveryPhoto";
import { EditAddressSheet } from "@/src/components/EditAddressSheet";
import { Button, ErrorState, Ionicons, Loading, Sheet, StatusBadge, useToast } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { PAYMENT_LABEL, STATUS_FLOW, STATUS_LABEL, statusColor } from "@/src/status";
import { makeStyles, useTheme } from "@/src/theme";

// Business view of an order: status, courier name/photo/phone. No courier location.
export default function BizOrderDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [addrOpen, setAddrOpen] = useState(false);
  const q = useQuery({
    queryKey: ["biz-order", id],
    queryFn: () => api<Omit<Order, "courier"> & { courier: CourierCard | null }>(`/biz/orders/${id}`),
    refetchInterval: 8000,
  });
  const cancel = useMutation({
    mutationFn: () => api<Order>(`/biz/orders/${id}/cancel`, { method: "PATCH" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["biz-order", id] });
      qc.invalidateQueries({ queryKey: ["biz-orders"] });
      setCancelOpen(false);
      toast("Pedido cancelado");
    },
    onError: (e: Error) => toast(e.message, "error"),
  });
  const o = q.data;
  const reached = (st: OrderStatus) => o?.history.find((h) => h.status === st);
  const canCancel = o?.status === "nuevo" || o?.status === "preparacion";

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <Pressable testID="back-button" onPress={() => (router.canGoBack() ? router.back() : router.replace("/biz"))} style={s.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={s.title}>Pedido #{o ? num(o.number) : ""}</Text>
        <View style={{ flex: 1 }} />
        {canCancel && (
          <Pressable testID="biz-cancel-order-button" onPress={() => setCancelOpen(true)} style={s.cancelBtn}>
            <Text style={s.cancelText}>Cancelar</Text>
          </Pressable>
        )}
      </View>
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !o ? (
        <ErrorState message="No pudimos cargar el pedido" onRetry={() => q.refetch()} />
      ) : (
        <ScrollView contentContainerStyle={[s.content, { paddingBottom: insets.bottom + space.xl }]}>
          <View style={s.rowBetween}>
            <StatusBadge testID="biz-order-status" status={o.status} />
            <Text style={s.muted}>{format(new Date(o.created_at), "dd/MM HH:mm")}</Text>
          </View>

          <View testID="biz-courier-card" style={s.card}>
            <Text style={s.cardTitle}>Repartidor</Text>
            {o.courier ? (
              <View style={s.courierRow}>
                <Avatar testID="biz-courier-photo" userId={o.courier.id} name={o.courier.name} hasPhoto={o.courier.has_photo} size={56} />
                <View style={{ flex: 1 }}>
                  <Text testID="biz-courier-name" style={s.strong}>{o.courier.name}</Text>
                  <Text style={s.muted}>{o.courier.vehicle ?? ""}{o.courier.phone ? ` · ${o.courier.phone}` : ""}</Text>
                </View>
                {!!o.courier.phone && o.status !== "cancelado" && (
                  <Pressable testID="biz-call-courier" onPress={() => Linking.openURL(`tel:${o.courier?.phone}`)} style={s.callBtn}>
                    <Ionicons name="call" size={20} color={colors.onBrandPrimary} />
                  </Pressable>
                )}
              </View>
            ) : (
              <View style={s.courierRow}>
                <Ionicons name="hourglass-outline" size={22} color={colors.warning} />
                <Text style={[s.info, { color: colors.warning }]}>
                  {o.status === "cancelado" ? "Pedido cancelado" : o.open ? "Avisamos a los repartidores. Esperando que uno acepte…" : "Aún sin repartidor asignado."}
                </Text>
              </View>
            )}
          </View>

          <View style={s.card}>
            <Text style={s.cardTitle}>Seguimiento</Text>
            {(o.status === "cancelado" ? [...STATUS_FLOW.filter((st) => reached(st)), "cancelado" as OrderStatus] : STATUS_FLOW).map((st) => {
              const h = reached(st);
              return (
                <View key={st} style={s.tlRow}>
                  <View style={[s.tlDot, { backgroundColor: h ? statusColor(st, colors) : colors.surfaceSecondary, borderColor: h ? statusColor(st, colors) : colors.borderStrong }]} />
                  <Text style={[s.tlLabel, !h && { color: colors.muted }]}>{STATUS_LABEL[st]}</Text>
                  {h && <Text style={s.muted}>{format(new Date(h.at), "HH:mm")}</Text>}
                </View>
              );
            })}
          </View>

          <View style={s.card}>
            <Text style={s.cardTitle}>Cliente</Text>
            <Text style={s.strong}>{o.customer_name}</Text>
            <Text style={s.info}>{o.address}</Text>
            {o.status !== "entregado" && o.status !== "cancelado" && (
              <Button testID="biz-edit-address" title="Cambiar dirección" icon="create-outline" variant="ghost" onPress={() => setAddrOpen(true)} />
            )}
            {!!o.notes && <Text style={s.info}>{o.notes}</Text>}
            <View style={[s.rowBetween, s.totalRow]}>
              <Text style={s.muted}>{PAYMENT_LABEL[o.payment_method ?? "efectivo"]} · pedido {(o.amount ?? 0) > 0 ? money(o.amount ?? 0) : "sin monto"}</Text>
            </View>
            <View testID="biz-fee-row" style={s.rowBetween}>
              <Text style={s.muted}>Envío{o.distance_km != null ? ` · ${o.distance_km.toFixed(2)} km` : ""}</Text>
              <Text style={s.total}>{money(o.delivery_fee)}</Text>
            </View>
          </View>

          {(o.incidents?.length ?? 0) > 0 && (
            <View testID="biz-incidents" style={s.card}>
              <Text style={[s.cardTitle, { color: colors.error }]}>Incidencias del repartidor</Text>
              {o.incidents?.map((inc, i) => (
                <Text key={i} style={s.info}>{format(new Date(inc.at), "HH:mm")} · {inc.by}: {inc.label}{inc.note ? ` — ${inc.note}` : ""}</Text>
              ))}
            </View>
          )}

          {(!!o.delivery_photo || !!o.delivery_note) && (
            <View style={s.card}>
              <Text style={s.cardTitle}>Comprobante de entrega</Text>
              {!!o.delivery_photo && <DeliveryPhoto orderId={o.id} style={s.proof} />}
              {!!o.delivery_note && <Text style={s.info}>{o.delivery_note}</Text>}
            </View>
          )}
        </ScrollView>
      )}
      {!!o && (
        <EditAddressSheet visible={addrOpen} onClose={() => setAddrOpen(false)} path={`/biz/orders/${o.id}/address`} current={o.address}
          onSaved={() => { qc.invalidateQueries({ queryKey: ["biz-order", id] }); qc.invalidateQueries({ queryKey: ["biz-orders"] }); }} />
      )}
      <Sheet testID="biz-cancel-sheet" visible={cancelOpen} onClose={() => setCancelOpen(false)} title="Cancelar pedido">
        <Text style={s.info}>¿Seguro que quieres cancelar este pedido? Avisaremos al repartidor.</Text>
        <Button testID="biz-confirm-cancel" title="Sí, cancelar" variant="danger" loading={cancel.isPending} onPress={() => cancel.mutate()} />
      </Sheet>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: space.xs, paddingHorizontal: space.sm, paddingBottom: space.sm, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: font.extrabold, fontSize: 22, color: c.onSurface },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  cancelBtn: { height: 44, paddingHorizontal: space.md, justifyContent: "center" },
  cancelText: { fontFamily: font.semibold, fontSize: 14, color: c.error },
  content: { padding: space.lg, gap: space.md },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, padding: space.lg, gap: space.sm },
  cardTitle: { fontFamily: font.bold, fontSize: 15, color: c.onSurface },
  courierRow: { flexDirection: "row", alignItems: "center", gap: space.md },
  callBtn: { width: 48, height: 48, borderRadius: 24, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  strong: { fontFamily: font.bold, fontSize: 16, color: c.onSurface },
  muted: { fontFamily: font.medium, fontSize: 13, color: c.muted },
  info: { fontFamily: font.medium, fontSize: 14, color: c.onSurfaceTertiary, flex: 1 },
  tlRow: { flexDirection: "row", alignItems: "center", gap: space.md, minHeight: 32 },
  tlDot: { width: 14, height: 14, borderRadius: 7, borderWidth: 2 },
  tlLabel: { fontFamily: font.semibold, fontSize: 14, color: c.onSurface, flex: 1 },
  totalRow: { borderTopWidth: 1, borderTopColor: c.divider, paddingTop: space.sm, marginTop: space.xs },
  total: { fontFamily: font.extrabold, fontSize: 20, color: c.onSurface },
  proof: { width: "100%", aspectRatio: 4 / 3, borderRadius: radius.md },
}));
