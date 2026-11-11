import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Business, CourierCard, money, Order, PaymentMethod, num } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Avatar } from "@/src/components/Avatar";
import { AddressInput, PickedAddress } from "@/src/components/AddressInput";
import { PAYMENT_LABEL, PAYMENT_METHODS } from "@/src/status";
import { CalendarSheet } from "@/src/components/CalendarSheet";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import { Button, Chip, EmptyState, Field, Ionicons, Loading, useToast } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

export default function NewOrder() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();

  const { user } = useAuth();
  const isBiz = user?.role === "business";
  const biz = useQuery({
    queryKey: [isBiz ? "biz-me-list" : "businesses"],
    queryFn: async () => (isBiz ? [await api<Business>("/biz/me")] : api<Business[]>("/businesses")),
  });
  const couriers = useQuery({
    queryKey: [isBiz ? "biz-couriers" : "couriers"],
    queryFn: () => api<(CourierCard & { profile_photo?: string | null })[]>(isBiz ? "/biz/couriers" : "/couriers"),
  });
  // Default: send to every online courier (first to accept takes it).
  const [open, setOpen] = useState(true);
  const [bizId, setBizId] = useState<string | null>(null);
  useEffect(() => {
    if (!bizId && biz.data?.length) setBizId(biz.data[0].id);
  }, [biz.data, bizId]);
  const selBiz = biz.data?.find((b) => b.id === bizId);
  // Owner: pre-fill the business's fixed delivery fee.
  useEffect(() => {
    if (!isBiz && selBiz?.default_fee) setFee(String(selBiz.default_fee).replace(".", ","));
  }, [isBiz, selBiz?.id, selBiz?.default_fee]);
  const [dest, setDest] = useState<PickedAddress | null>(null);
  const [quoteKm, setQuoteKm] = useState<number | null>(null);
  const [bizFee, setBizFee] = useState<number | null>(null);
  const [quoting, setQuoting] = useState(false);
  // Price from the shortest road route as soon as the delivery point is known.
  // Owner: pre-fills the editable fee (km pricing). Business: shows the fee it will be charged.
  useEffect(() => {
    setQuoteKm(null);
    setBizFee(null);
    if (!dest || (!isBiz && (!selBiz || selBiz.pricing_mode !== "km"))) return;
    let live = true;
    setQuoting(true);
    api<{ fee: number; distance_km: number | null }>(isBiz ? `/biz/quote?lat=${dest.lat}&lng=${dest.lng}` : `/businesses/${selBiz!.id}/quote?lat=${dest.lat}&lng=${dest.lng}`)
      .then((r) => {
        if (!live) return;
        if (isBiz) setBizFee(r.fee);
        else setFee(String(r.fee).replace(".", ","));
        setQuoteKm(r.distance_km);
      })
      .catch(() => {})
      .finally(() => live && setQuoting(false));
    return () => { live = false; };
  }, [isBiz, selBiz, dest]);
  const [amount, setAmount] = useState("");
  const [customer, setCustomer] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [fee, setFee] = useState("2");
  const [courierId, setCourierId] = useState<string | null>(null);
  const [userPick, setUserPick] = useState<PaymentMethod | null>(null);
  const [schedDate, setSchedDate] = useState<Date | null>(null);
  const [schedTime, setSchedTime] = useState("12:00");
  const [calOpen, setCalOpen] = useState(false);
  const scheduledFor = (() => {
    if (!schedDate) return null;
    const m = schedTime.match(/^(\d{1,2}):(\d{2})$/);
    const d = new Date(schedDate);
    d.setHours(m ? Math.min(23, +m[1]) : 12, m ? Math.min(59, +m[2]) : 0, 0, 0);
    return d;
  })();
  const [error, setError] = useState("");

  const feeNum = parseFloat(fee.replace(",", ".")) || 0;
  const subtotal = parseFloat(amount.replace(",", ".")) || 0;
  // No amount to collect -> always "Pagado"; with an amount -> the user's choice, else "Efectivo".
  const payment: PaymentMethod = subtotal <= 0 ? "pagado" : userPick ?? "efectivo";

  const create = useMutation({
    mutationFn: () =>
      api<Order>(isBiz ? "/biz/orders" : "/orders", {
        method: "POST",
        body: {
          business_id: bizId,
          customer_name: customer,
          customer_phone: phone,
          address,
          dest_lat: dest?.lat ?? null,
          dest_lng: dest?.lng ?? null,
          notes,
          delivery_fee: isBiz ? 0 : feeNum,
          courier_id: courierId,
          payment_method: payment,
          scheduled_for: scheduledFor ? scheduledFor.toISOString() : null,
          amount: subtotal,
          open: !courierId && open,
        },
      }),
    onSuccess: (o) => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["biz-orders"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast(`Orden #${num(o.number)} creada`);
      router.replace(isBiz ? `/biz-order/${o.id}` : `/order/${o.id}`);
    },
    onError: (e: Error) => setError(e.message),
  });

  const submit = () => {
    setError("");
    if (!customer.trim() || !address.trim()) return setError("Completa nombre del cliente y dirección");
    create.mutate();
  };

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <Pressable testID="back-button" onPress={() => router.back()} style={s.iconBtn}>
          <Ionicons name="close" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={s.title}>Nueva orden</Text>
      </View>
      {biz.isLoading ? (
        <Loading />
      ) : biz.data?.length === 0 ? (
        <EmptyState title="Primero crea un comercio" subtitle="Ve a Gestión y agrega un comercio." />
      ) : (
        <KeyboardAwareScrollView bottomOffset={120} keyboardShouldPersistTaps="handled" contentContainerStyle={s.content}>
          {!isBiz && (
            <>
              <Text style={s.section}>Comercio</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipRow} contentContainerStyle={s.chips}>
                {biz.data?.map((b) => (
                  <Chip key={b.id} testID={`order-business-${b.id}`} label={b.name} selected={bizId === b.id} onPress={() => setBizId(b.id)} />
                ))}
              </ScrollView>
            </>
          )}

          <Text style={s.section}>Cliente</Text>
          <View style={s.form}>
            <Field testID="customer-name-input" label="Nombre" value={customer} onChangeText={setCustomer} placeholder="Ej. María López" />
            <Field testID="customer-phone-input" label="Teléfono" value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="Opcional" />
            <AddressInput
              testID="customer-address"
              label="Dirección de entrega"
              value={address}
              near={selBiz}
              picked={!!dest}
              placeholder="Escribe calle y número y elige de la lista"
              onChangeText={(t) => {
                setAddress(t);
                setDest(null);
              }}
              onPick={(p) => {
                setAddress(p.address);
                setDest(p);
              }}
            />
            <Field testID="order-notes-input" label="Notas (piso, puerta…)" value={notes} onChangeText={setNotes} placeholder="Ej. 3º B, tocar timbre 2 veces" multiline />
            <Field testID="order-amount-input" label="Monto del pedido (opcional)" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" placeholder="0,00" />
            {!isBiz && <Field testID="delivery-fee-input" label="Costo de envío" value={fee} onChangeText={setFee} keyboardType="decimal-pad" />}
            {!isBiz && quoteKm != null && <Text testID="quote-km" style={s.muted}>Ruta más corta: {quoteKm.toFixed(2)} km · precio calculado por km</Text>}
            {isBiz && (
              <View testID="biz-quote" style={s.quoteBox}>
                <Ionicons name="bicycle-outline" size={20} color={colors.brandPrimary} />
                <Text style={s.quoteText}>
                  {!dest ? "Elige la dirección de la lista para ver el precio del envío"
                    : quoting ? "Calculando precio del envío…"
                    : bizFee != null ? `Envío: ${money(bizFee)}${quoteKm != null ? ` · ${quoteKm.toFixed(2).replace(".", ",")} km` : ""}` : "No pudimos calcular el envío"}
                </Text>
              </View>
            )}
          </View>

          <Text style={s.section}>¿Cuándo?</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipRow} contentContainerStyle={s.chips}>
            <Chip testID="schedule-now" label="Ahora" selected={!schedDate} onPress={() => setSchedDate(null)} />
            <Chip
              testID="schedule-pick-date"
              label={schedDate ? format(schedDate, "EEE d MMM", { locale: es }) : "Programar otro día"}
              selected={!!schedDate}
              onPress={() => setCalOpen(true)}
            />
          </ScrollView>
          {!!schedDate && (
            <View style={s.form}>
              <Field testID="schedule-time-input" label="Hora (HH:MM)" value={schedTime} onChangeText={setSchedTime} placeholder="12:00" maxLength={5} />
            </View>
          )}

          <Text style={s.section}>Forma de pago</Text>
          {subtotal <= 0 && <Text testID="payment-auto-hint" style={[s.muted, { paddingHorizontal: space.lg }]}>Sin importe a cobrar: el pedido queda como pagado.</Text>}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipRow} contentContainerStyle={s.chips}>
            {PAYMENT_METHODS.filter((p) => subtotal > 0 || p === "pagado").map((p) => (
              <Chip key={p} testID={`order-payment-${p}`} label={PAYMENT_LABEL[p]} selected={payment === p} onPress={() => { if (subtotal > 0) setUserPick(p); }} />
            ))}
          </ScrollView>

          <Text style={s.section}>Repartidor</Text>
          <View style={s.form}>
            <Pressable testID="order-courier-open" onPress={() => { setCourierId(null); setOpen(true); }} style={[s.option, !courierId && open && s.optionOn]}>
              <View style={s.openIcon}><Ionicons name="megaphone-outline" size={20} color={colors.onBrandSecondary} /></View>
              <View style={{ flex: 1 }}>
                <Text style={s.prodName}>Enviar a todos los repartidores en línea</Text>
                <Text style={s.prodPrice}>Les avisamos a todos y el primero que acepte se lo lleva. O elige uno abajo.</Text>
              </View>
            </Pressable>
            {!isBiz && (
              <Pressable testID="order-courier-none" onPress={() => { setCourierId(null); setOpen(false); }} style={[s.option, !courierId && !open && s.optionOn]}>
                <View style={s.openIcon}><Ionicons name="time-outline" size={20} color={colors.onBrandSecondary} /></View>
                <Text style={[s.prodName, { flex: 1 }]}>Sin asignar (lo asigno después)</Text>
              </Pressable>
            )}
            {couriers.data?.map((c) => (
              <Pressable key={c.id} testID={`order-courier-${c.id}`} onPress={() => setCourierId(c.id)} style={[s.option, courierId === c.id && s.optionOn]}>
                <Avatar userId={c.id} name={c.name} hasPhoto={c.has_photo ?? !!c.profile_photo} version={c.profile_photo} size={40} />
                <View style={{ flex: 1 }}>
                  <Text style={s.prodName}>{c.name}</Text>
                  <Text style={s.prodPrice}>{c.online ? "● En línea" : "Desconectado"}{c.vehicle ? ` · ${c.vehicle}` : ""}</Text>
                </View>
                {courierId === c.id && <Ionicons name="checkmark-circle" size={22} color={colors.brandPrimary} />}
              </Pressable>
            ))}
          </View>
        </KeyboardAwareScrollView>
      )}
      <CalendarSheet visible={calOpen} value={schedDate ?? new Date()} allowFuture onClose={() => setCalOpen(false)} onSelect={(d) => setSchedDate(d)} />
      {!!biz.data?.length && (
        <KeyboardStickyView offset={{ closed: 0, opened: insets.bottom }}>
          <View style={[s.footer, { paddingBottom: insets.bottom + space.md }]}>
            {!!error && <Text testID="order-error" style={s.error}>{error}</Text>}
            <View style={s.totals}>
              <Text style={s.muted}>{isBiz ? (bizFee != null ? `Pedido ${money(subtotal)} · envío ${money(bizFee)}` : "Monto del pedido") : `Pedido ${money(subtotal)} · envío ${money(feeNum)}`}</Text>
              <Text testID="order-total" style={s.total}>{money(isBiz ? subtotal + (bizFee ?? 0) : subtotal + feeNum)}</Text>
            </View>
            <Button testID="create-order-submit" title="Crear orden" size="lg" onPress={submit} loading={create.isPending} />
          </View>
        </KeyboardStickyView>
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: space.xs, paddingHorizontal: space.sm, paddingBottom: space.sm, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: font.extrabold, fontSize: 22, color: c.onSurface },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  content: { paddingVertical: space.md, paddingBottom: space.xl },
  section: { fontFamily: font.bold, fontSize: 16, color: c.onSurface, paddingHorizontal: space.lg, marginTop: space.lg, marginBottom: space.xs },
  chipRow: { height: 56, flexGrow: 0 },
  chips: { gap: space.sm, paddingHorizontal: space.lg, alignItems: "center" },
  card: { marginHorizontal: space.lg, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, paddingHorizontal: space.lg },
  prodRow: { flexDirection: "row", alignItems: "center", paddingVertical: space.md },
  divider: { borderTopWidth: 1, borderTopColor: c.divider },
  prodName: { fontFamily: font.semibold, fontSize: 15, color: c.onSurface },
  prodPrice: { fontFamily: font.medium, fontSize: 13, color: c.muted },
  stepper: { flexDirection: "row", alignItems: "center", gap: space.sm },
  stepBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  qty: { fontFamily: font.bold, fontSize: 16, color: c.onSurface, minWidth: 20, textAlign: "center" },
  form: { paddingHorizontal: space.lg, gap: space.md },
  muted: { fontFamily: font.medium, fontSize: 13, color: c.muted, paddingVertical: space.md },
  quoteBox: { flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 48, padding: space.md, borderRadius: radius.md, backgroundColor: c.brandTertiary },
  quoteText: { flex: 1, fontFamily: font.bold, fontSize: 14, color: c.onBrandTertiary },
  footer: { backgroundColor: c.surfaceSecondary, borderTopWidth: 1, borderTopColor: c.border, paddingHorizontal: space.lg, paddingTop: space.md, gap: space.sm },
  totals: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  total: { fontFamily: font.extrabold, fontSize: 22, color: c.onSurface },
  error: { fontFamily: font.semibold, fontSize: 13, color: c.error },
  option: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.md, borderRadius: radius.md, borderWidth: 1.5, borderColor: c.border, backgroundColor: c.surfaceSecondary, minHeight: 60 },
  optionOn: { borderColor: c.brandPrimary },
  openIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center" },
}));
