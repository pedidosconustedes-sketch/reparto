import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Haptics from "expo-haptics";
import { useLocalSearchParams, useRouter } from "expo-router";
import { format } from "date-fns";
import { useState } from "react";
import { Linking, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, money, Order, OrderStatus, PaymentMethod, User, num } from "@/src/api";
import { TripMap } from "@/src/components/TripMap";
import { Avatar } from "@/src/components/Avatar";
import { DeliveryPhoto } from "@/src/components/DeliveryPhoto";
import { EditAddressSheet } from "@/src/components/EditAddressSheet";
import { Button, Chip, ErrorState, Field, Ionicons, Loading, Sheet, StatusBadge, useToast } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { deliveryMinutes, durationLabel, nextStatus, PAYMENT_LABEL, PAYMENT_METHODS, STATUS_FLOW, STATUS_LABEL, statusColor } from "@/src/status";
import { makeStyles, useTheme } from "@/src/theme";

export default function OrderDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const [assignOpen, setAssignOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [addrOpen, setAddrOpen] = useState(false);

  const q = useQuery({ queryKey: ["order", id], queryFn: () => api<Order>(`/orders/${id}`), refetchInterval: 10000 });
  const couriers = useQuery({ queryKey: ["couriers"], queryFn: () => api<User[]>("/couriers"), enabled: assignOpen });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["order", id] });
    qc.invalidateQueries({ queryKey: ["orders"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const setStatus = useMutation({
    mutationFn: (status: OrderStatus) => api<Order>(`/orders/${id}/status`, { method: "PATCH", body: { status } }),
    onSuccess: (o) => {
      if (Platform.OS !== "web") Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      refresh();
      setCancelOpen(false);
      toast(`Estado: ${STATUS_LABEL[o.status]}`);
    },
    onError: (e: Error) => toast(e.message, "error"),
  });
  const setPayment = useMutation({
    mutationFn: (payment_method: PaymentMethod) => api<Order>(`/orders/${id}/payment`, { method: "PATCH", body: { payment_method } }),
    onSuccess: (o) => {
      refresh();
      toast(`Pago: ${PAYMENT_LABEL[o.payment_method]}`);
    },
    onError: (e: Error) => toast(e.message, "error"),
  });
  const assign = useMutation({
    mutationFn: (courier_id: string | null) => api<Order>(`/orders/${id}/assign`, { method: "PATCH", body: { courier_id } }),
    onSuccess: (o) => {
      refresh();
      setAssignOpen(false);
      toast(o.courier_name ? `Asignada a ${o.courier_name}` : "Repartidor removido");
    },
    onError: (e: Error) => toast(e.message, "error"),
  });

  const [feeOpen, setFeeOpen] = useState(false);
  const [feeText, setFeeText] = useState("");
  const saveFee = useMutation({
    mutationFn: () => api<Order>(`/orders/${id}/fee`, { method: "PATCH", body: { delivery_fee: parseFloat(feeText.replace(",", ".")) || 0 } }),
    onSuccess: () => {
      refresh();
      setFeeOpen(false);
      toast("Precio del envío actualizado");
    },
    onError: (e: Error) => toast(e.message, "error"),
  });

  const o = q.data;
  const next = o ? nextStatus(o.status) : null;
  const closed = o?.status === "entregado" || o?.status === "cancelado";
  const reached = (st: OrderStatus) => o?.history.find((h) => h.status === st);

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <Pressable testID="back-button" onPress={() => router.back()} style={s.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={s.title}>Orden #{o ? num(o.number) : ""}</Text>
        <View style={{ flex: 1 }} />
        {o && !closed && (
          <Pressable testID="cancel-order-button" onPress={() => setCancelOpen(true)} style={s.cancelBtn}>
            <Text style={s.cancelText}>Cancelar</Text>
          </Pressable>
        )}
      </View>
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !o ? (
        <ErrorState message="No pudimos cargar la orden" onRetry={() => q.refetch()} />
      ) : (
        <>
          <ScrollView contentContainerStyle={s.content}>
            <View style={s.rowBetween}>
              <StatusBadge testID="order-status-badge" status={o.status} />
              <Text style={s.muted}>{format(new Date(o.created_at), "dd/MM HH:mm")}</Text>
            </View>
            {(o.incidents?.length ?? 0) > 0 && (
              <View testID="order-incidents" style={s.card}>
                <Text style={[s.cardTitle, { color: colors.error }]}>Incidencias ({o.incidents?.length})</Text>
                {o.incidents?.map((inc, i) => (
                  <Text key={i} testID={`incident-${i}`} style={s.tlLabel}>
                    {format(new Date(inc.at), "HH:mm")} · {inc.by}: {inc.label}{inc.note ? ` — ${inc.note}` : ""}
                  </Text>
                ))}
              </View>
            )}
            {o.distance_km != null && <Text testID="order-distance" style={s.tlLabel}>Distancia por carretera: {o.distance_km.toFixed(2)} km</Text>}

            <View style={s.card}>
              <Text style={s.cardTitle}>Seguimiento</Text>
              {STATUS_FLOW.map((st, i) => {
                const h = reached(st);
                const col = h ? statusColor(st, colors) : colors.borderStrong;
                return (
                  <View key={st} style={s.tlRow}>
                    <View style={s.tlRail}>
                      <View style={[s.tlDot, { backgroundColor: h ? col : colors.surfaceSecondary, borderColor: col }]} />
                      {i < STATUS_FLOW.length - 1 && <View style={[s.tlLine, { backgroundColor: reached(STATUS_FLOW[i + 1]) ? col : colors.border }]} />}
                    </View>
                    <View style={s.tlText}>
                      <Text style={[s.tlLabel, !h && { color: colors.muted }]}>{STATUS_LABEL[st]}</Text>
                      {h && <Text style={s.muted}>{format(new Date(h.at), "HH:mm")}</Text>}
                    </View>
                  </View>
                );
              })}
              {o.status === "cancelado" && <Text style={[s.tlLabel, { color: colors.error }]}>Orden cancelada</Text>}
              {deliveryMinutes(o.history) != null && (
                <View testID="delivery-duration" style={s.durationBox}>
                  <Ionicons name="stopwatch-outline" size={20} color={colors.brandPrimary} />
                  <Text style={s.durationText}>
                    Entregado en {durationLabel(deliveryMinutes(o.history) as number)} desde que lo recogió
                  </Text>
                </View>
              )}
            </View>

            <View style={s.card}>
              <Text style={s.cardTitle}>{o.business_name}</Text>
              {o.items.map((it, i) => (
                <View key={i} style={s.itemRow}>
                  <Text style={s.itemQty}>{it.qty}×</Text>
                  <Text style={s.itemName}>{it.name}</Text>
                  <Text style={s.itemPrice}>{money(it.price * it.qty)}</Text>
                </View>
              ))}
              {o.items.length === 0 && (
                <View style={s.itemRow}>
                  <Text style={s.itemQty} />
                  <Text style={s.itemName}>Pedido</Text>
                  <Text style={s.itemPrice}>{(o.amount ?? 0) > 0 ? money(o.amount ?? 0) : "Sin monto"}</Text>
                </View>
              )}
              <Pressable
                testID="edit-fee-button"
                disabled={o.courier_paid}
                onPress={() => { setFeeText(String(o.delivery_fee).replace(".", ",")); setFeeOpen(true); }}
                style={[s.itemRow, { minHeight: 44, alignItems: "center" }]}
              >
                <Text style={s.itemQty} />
                <Text style={[s.itemName, { color: colors.muted }]}>Envío{o.created_by === "business" ? " (pedido del comercio)" : ""}</Text>
                <Text style={s.itemPrice}>{money(o.delivery_fee)}</Text>
                {!o.courier_paid && <Ionicons name="create-outline" size={16} color={colors.brandPrimary} />}
              </Pressable>
              <View style={[s.rowBetween, s.totalRow]}>
                <Text style={s.cardTitle}>Total</Text>
                <Text testID="order-detail-total" style={s.total}>{money(o.total)}</Text>
              </View>
            </View>

            <View style={s.card}>
              <Text style={s.cardTitle}>Cliente</Text>
              <Text style={s.strong}>{o.customer_name}</Text>
              <View style={s.infoRow}>
                <Ionicons name="location-outline" size={16} color={colors.muted} />
                <Text style={s.info}>{o.address}</Text>
              </View>
              {!closed && (
                <Button testID="edit-address-button" title="Cambiar dirección" icon="create-outline" variant="ghost" onPress={() => setAddrOpen(true)} />
              )}
              {!!o.notes && (
                <View style={s.infoRow}>
                  <Ionicons name="document-text-outline" size={16} color={colors.muted} />
                  <Text style={s.info}>{o.notes}</Text>
                </View>
              )}
              {!!o.customer_phone && (
                <Pressable testID="call-customer-button" onPress={() => Linking.openURL(`tel:${o.customer_phone}`)} style={s.pill}>
                  <Ionicons name="call" size={14} color={colors.onBrandSecondary} />
                  <Text style={s.pillText}>{o.customer_phone}</Text>
                </Pressable>
              )}
            </View>

            <View style={s.card}>
              <Text style={s.cardTitle}>Forma de pago</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
                {PAYMENT_METHODS.map((p) => (
                  <Chip key={p} testID={`detail-payment-${p}`} label={PAYMENT_LABEL[p]} selected={(o.payment_method ?? "efectivo") === p} onPress={() => setPayment.mutate(p)} />
                ))}
              </ScrollView>
            </View>

            {(!!o.delivery_photo || !!o.delivery_note) && (
              <View testID="delivery-proof-card" style={s.card}>
                <Text style={s.cardTitle}>Comprobante de entrega</Text>
                {!!o.delivery_photo && <DeliveryPhoto orderId={o.id} style={s.proofPhoto} />}
                {!!o.delivery_note && (
                  <View style={s.infoRow}>
                    <Ionicons name="chatbubble-ellipses-outline" size={16} color={colors.muted} />
                    <Text testID="delivery-note-text" style={s.info}>{o.delivery_note}</Text>
                  </View>
                )}
              </View>
            )}

            <View testID="route-card" style={s.card}>
              <Text style={s.cardTitle}>Ruta</Text>
              <TripMap
                style={s.map}
                points={[
                  { kind: "courier", lat: o.courier?.lat, lng: o.courier?.lng, title: o.courier?.name ?? "Sin repartidor" },
                  { kind: "pickup", lat: o.pickup_lat, lng: o.pickup_lng, title: `${o.business_name} · ${o.pickup_address ?? ""}` },
                  { kind: "dest", lat: o.dest_lat, lng: o.dest_lng, title: o.address },
                ]}
              />
            </View>

            <View style={s.card}>
              <View style={s.rowBetween}>
                <Text style={s.cardTitle}>Repartidor</Text>
                {!closed && (
                  <Pressable testID="change-courier-button" onPress={() => setAssignOpen(true)} style={s.linkBtn}>
                    <Text style={s.link}>{o.courier ? "Cambiar" : "Asignar"}</Text>
                  </Pressable>
                )}
              </View>
              {o.courier ? (
                <>
                  <View style={s.infoRow}>
                    <Avatar userId={o.courier.id} name={o.courier.name} hasPhoto={!!o.courier.profile_photo} version={o.courier.profile_photo} size={44} />
                    <View style={[s.dot, { backgroundColor: o.courier.online ? colors.success : colors.muted }]} />
                    <Text testID="assigned-courier-name" style={s.strong}>{o.courier.name}</Text>
                    <Text style={s.muted}>· {o.courier.vehicle}</Text>
                  </View>
                </>
              ) : (
                <Text style={s.muted}>Aún sin repartidor asignado.</Text>
              )}
            </View>
          </ScrollView>
          {!closed && (
            <View style={[s.footer, { paddingBottom: insets.bottom + space.md }]}>
              {!o.courier_id && (
                <Button testID="assign-courier-button" title="Asignar repartidor" icon="bicycle" variant="secondary" onPress={() => setAssignOpen(true)} style={{ flex: 1 }} />
              )}
              {next && (
                <Button
                  testID="advance-status-button"
                  title={`Pasar a ${STATUS_LABEL[next]}`}
                  icon="arrow-forward"
                  onPress={() => setStatus.mutate(next)}
                  loading={setStatus.isPending}
                  style={{ flex: 1 }}
                />
              )}
            </View>
          )}
        </>
      )}

      <Sheet testID="fee-sheet" visible={feeOpen} onClose={() => setFeeOpen(false)} title="Precio del envío">
        <Field testID="fee-input" label="Lo que cobra el repartidor (€)" value={feeText} onChangeText={setFeeText} keyboardType="decimal-pad" />
        <Button testID="fee-save" title="Guardar" loading={saveFee.isPending} onPress={() => saveFee.mutate()} />
      </Sheet>
      <Sheet testID="assign-sheet" visible={assignOpen} onClose={() => setAssignOpen(false)} title="Asignar repartidor">
        {couriers.isLoading && <Loading />}
        {couriers.data?.length === 0 && <Text style={s.muted}>No tienes repartidores. Agrégalos en Gestión.</Text>}
        {couriers.data?.map((c) => (
          <Pressable key={c.id} testID={`assign-option-${c.id}`} onPress={() => assign.mutate(c.id)} style={[s.option, o?.courier_id === c.id && { borderColor: colors.brandPrimary }]}>
            <View style={[s.dot, { backgroundColor: c.online ? colors.success : colors.muted }]} />
            <View style={{ flex: 1 }}>
              <Text style={s.strong}>{c.name}</Text>
              <Text style={s.muted}>{c.online ? "En línea" : "Desconectado"} · {c.active_orders ?? 0} entregas activas</Text>
            </View>
            {o?.courier_id === c.id && <Ionicons name="checkmark-circle" size={22} color={colors.brandPrimary} />}
          </Pressable>
        ))}
        {!!o?.courier_id && <Button testID="unassign-courier-button" title="Quitar repartidor" variant="ghost" onPress={() => assign.mutate(null)} />}
      </Sheet>

      {!!o && (
        <EditAddressSheet visible={addrOpen} onClose={() => setAddrOpen(false)} path={`/orders/${o.id}/address`} current={o.address} onSaved={refresh} />
      )}
      <Sheet testID="cancel-sheet" visible={cancelOpen} onClose={() => setCancelOpen(false)} title="Cancelar orden">
        <Text style={s.info}>¿Seguro que quieres cancelar esta orden? No se puede deshacer.</Text>
        <Button testID="confirm-cancel-order" title="Sí, cancelar orden" variant="danger" loading={setStatus.isPending} onPress={() => setStatus.mutate("cancelado")} />
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
  content: { padding: space.lg, gap: space.md, paddingBottom: space.xl },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, padding: space.lg, gap: space.sm },
  cardTitle: { fontFamily: font.bold, fontSize: 15, color: c.onSurface },
  durationBox: { flexDirection: "row", alignItems: "center", gap: space.sm, backgroundColor: c.brandTertiary, borderRadius: radius.md, padding: space.md, marginTop: space.xs },
  durationText: { flex: 1, fontFamily: font.bold, fontSize: 14, color: c.onBrandTertiary },
  muted: { fontFamily: font.medium, fontSize: 13, color: c.muted },
  tlRow: { flexDirection: "row", gap: space.md, minHeight: 40 },
  tlRail: { alignItems: "center", width: 16 },
  tlDot: { width: 14, height: 14, borderRadius: 7, borderWidth: 2, marginTop: 3 },
  tlLine: { width: 2, flex: 1, marginVertical: 2 },
  tlText: { flex: 1, flexDirection: "row", justifyContent: "space-between" },
  tlLabel: { fontFamily: font.semibold, fontSize: 14, color: c.onSurface },
  itemRow: { flexDirection: "row", alignItems: "center", gap: space.sm },
  itemQty: { fontFamily: font.bold, fontSize: 14, color: c.brandPrimary, width: 28 },
  itemName: { fontFamily: font.medium, fontSize: 14, color: c.onSurface, flex: 1 },
  itemPrice: { fontFamily: font.semibold, fontSize: 14, color: c.onSurface },
  totalRow: { borderTopWidth: 1, borderTopColor: c.divider, paddingTop: space.sm, marginTop: space.xs },
  total: { fontFamily: font.extrabold, fontSize: 20, color: c.onSurface },
  strong: { fontFamily: font.bold, fontSize: 16, color: c.onSurface },
  infoRow: { flexDirection: "row", alignItems: "center", gap: space.sm },
  info: { fontFamily: font.medium, fontSize: 14, color: c.onSurfaceTertiary, flex: 1 },
  pill: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", backgroundColor: c.brandSecondary, paddingHorizontal: space.md, height: 44, borderRadius: radius.pill },
  pillText: { fontFamily: font.bold, fontSize: 13, color: c.onBrandSecondary },
  link: { fontFamily: font.bold, fontSize: 14, color: c.brandPrimary },
  linkBtn: { minHeight: 44, minWidth: 44, justifyContent: "center", alignItems: "flex-end" },
  dot: { width: 10, height: 10, borderRadius: 5 },
  map: { height: 220, borderRadius: radius.md, overflow: "hidden" },
  proofPhoto: { width: "100%", aspectRatio: 4 / 3, borderRadius: radius.md },
  footer: { flexDirection: "row", gap: space.sm, backgroundColor: c.surfaceSecondary, borderTopWidth: 1, borderTopColor: c.border, paddingHorizontal: space.lg, paddingTop: space.md },
  option: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.md, borderRadius: radius.md, borderWidth: 1.5, borderColor: c.border, minHeight: 60 },
}));
