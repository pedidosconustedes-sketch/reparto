import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Business, money, plural, User } from "@/src/api";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import { useAuth } from "@/src/auth";
import { Avatar } from "@/src/components/Avatar";
import { AdminsPanel } from "@/src/components/AdminsPanel";
import { NamedPhone, PhonesEditor } from "@/src/components/PhonesEditor";
import { AddressInput, PickedAddress } from "@/src/components/AddressInput";
import { BizPhoto } from "@/src/components/BizPhoto";
import { ChangePasswordSheet } from "@/src/components/ChangePasswordSheet";
import { Button, Chip, EmptyState, ErrorState, Field, Ionicons, Loading, Sheet, useToast } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme } from "@/src/theme";

type Payout = { courier_id: string; name: string; pending_total: number; pending_count: number; last_paid_at: string | null; last_paid_amount: number | null };

const CATEGORIES = ["Comida", "Cafetería", "Farmacia", "Almacén", "Tienda", "General"];
const VEHICLES = ["Moto", "Bicicleta", "Auto", "A pie"];

export default function Manage() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const { user, signOut } = useAuth();
  const [tab, setTab] = useState<"biz" | "couriers" | "admins">("biz");
  const [bizSheet, setBizSheet] = useState(false);
  const [courierSheet, setCourierSheet] = useState(false);
  const [del, setDel] = useState<User | null>(null);
  const [payTarget, setPayTarget] = useState<User | null>(null);
  const payouts = useQuery({
    queryKey: ["payouts"],
    queryFn: () => api<Payout[]>("/payouts"),
    enabled: tab === "couriers",
    refetchInterval: 15000,
  });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api<{ emergency_phones: NamedPhone[] }>("/settings") });
  const [sosOpen, setSosOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const [sosList, setSosList] = useState<NamedPhone[]>([]);
  const saveSos = useMutation({
    mutationFn: () => api("/settings", { method: "PUT", body: { emergency_phones: sosList.filter((p) => p.phone.trim()) } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      setSosOpen(false);
      toast("Teléfonos de emergencia guardados");
    },
    onError: (e: Error) => toast(e.message, "error"),
  });
  const payMap = Object.fromEntries((payouts.data ?? []).map((p) => [p.courier_id, p])) as Record<string, Payout | undefined>;
  const pay = useMutation({
    mutationFn: (id: string) => api<{ amount: number; count: number }>(`/payouts/${id}`, { method: "POST" }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["payouts"] });
      setPayTarget(null);
      toast(`Pago registrado: ${money(r.amount)}`);
    },
    onError: (e: Error) => toast(e.message, "error"),
  });

  const biz = useQuery({ queryKey: ["businesses"], queryFn: () => api<Business[]>("/businesses") });
  const couriers = useQuery({ queryKey: ["couriers"], queryFn: () => api<User[]>("/couriers") });
  const active = tab === "biz" ? biz : couriers;

  // business form
  const [bName, setBName] = useState("");
  const [bCat, setBCat] = useState("Comida");
  const [bAddr, setBAddr] = useState("");
  const [bPhone, setBPhone] = useState("");
  const [bFee, setBFee] = useState("");
  const [bPick, setBPick] = useState<PickedAddress | null>(null);
  const addBiz = useMutation({
    mutationFn: () =>
      api<Business>("/businesses", {
        method: "POST",
        body: { name: bName, category: bCat, address: bAddr, phone: bPhone, default_fee: parseFloat(bFee.replace(",", ".")) || 0, lat: bPick?.lat ?? null, lng: bPick?.lng ?? null },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["businesses"] });
      setBizSheet(false);
      setBName(""); setBAddr(""); setBPhone(""); setBFee(""); setBPick(null);
      toast("Comercio creado");
    },
    onError: (e: Error) => toast(e.message, "error"),
  });

  // courier form
  const [cName, setCName] = useState("");
  const [cPhone, setCPhone] = useState("");
  const [cPin, setCPin] = useState("");
  const [cVeh, setCVeh] = useState("Moto");
  const addCourier = useMutation({
    mutationFn: () => api<User>("/couriers", { method: "POST", body: { name: cName, phone: cPhone, pin: cPin, vehicle: cVeh } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["couriers"] });
      setCourierSheet(false);
      setCName(""); setCPhone(""); setCPin("");
      toast("Repartidor agregado");
    },
    onError: (e: Error) => toast(e.message, "error"),
  });
  const delCourier = useMutation({
    mutationFn: (id: string) => api(`/couriers/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["couriers"] });
      setDel(null);
      toast("Repartidor eliminado");
    },
  });

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.md }]}>
        <View style={s.headRow}>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>Gestión</Text>
            <Text style={s.sub} numberOfLines={1}>{user?.email}</Text>
          </View>
          <Pressable testID="change-password-button" accessibilityLabel="Cambiar contraseña" onPress={() => setPwOpen(true)} style={s.logout}>
            <Ionicons name="key-outline" size={20} color={colors.onSurface} />
          </Pressable>
          <Pressable testID="logout-button" onPress={signOut} style={s.logout}>
            <Ionicons name="log-out-outline" size={20} color={colors.error} />
            <Text style={s.logoutText}>Salir</Text>
          </Pressable>
        </View>
        <View style={s.segment}>
          {((user?.is_main ? ["biz", "couriers", "admins"] : ["biz", "couriers"]) as ("biz" | "couriers" | "admins")[]).map((t) => (
            <Pressable key={t} testID={`manage-tab-${t}`} onPress={() => setTab(t)} style={[s.segBtn, tab === t && s.segActive]}>
              <Text style={[s.segText, tab === t && s.segTextActive]}>{t === "biz" ? "Comercios" : t === "couriers" ? "Repartidores" : "Admins"}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      {tab === "admins" ? (
        <ScrollView contentContainerStyle={[s.list, { paddingBottom: bottomChrome + space.xl }]}>
          <AdminsPanel />
        </ScrollView>
      ) : active.isLoading ? (
        <Loading />
      ) : active.isError ? (
        <ErrorState message="No pudimos cargar los datos" onRetry={() => active.refetch()} />
      ) : (
        <ScrollView
          contentContainerStyle={[s.list, { paddingBottom: bottomChrome + space.xl }]}
          refreshControl={<RefreshControl refreshing={active.isRefetching} onRefresh={() => { active.refetch(); }} tintColor={colors.brandPrimary} />}
        >
          {(tab === "biz" || !user?.linked) && (
            <Button
              testID={tab === "biz" ? "add-business-button" : "add-courier-button"}
              title={tab === "biz" ? "Agregar comercio" : "Agregar repartidor"}
              icon="add"
              variant="secondary"
              onPress={() => (tab === "biz" ? setBizSheet(true) : setCourierSheet(true))}
            />
          )}
          {tab === "couriers" && (
            <Button
              testID="emergency-phones-button"
              title={`Teléfonos de emergencia (${settings.data?.emergency_phones.length ?? 0})`}
              icon="call"
              variant="ghost"
              onPress={() => {
                setSosList(settings.data?.emergency_phones ?? []);
                setSosOpen(true);
              }}
            />
          )}
          {tab === "biz"
            ? biz.data?.length === 0
              ? <EmptyState title="Aún no tienes comercios" subtitle="Agrega tu primer comercio para cargar su catálogo." />
              : biz.data?.map((b) => (
                  <Pressable key={b.id} testID={`business-row-${b.id}`} onPress={() => router.push(`/business/${b.id}`)} style={s.row}>
                    <BizPhoto businessId={b.id} photo={b.photo} size={44} testID={`business-photo-${b.id}`} />
                    <View style={{ flex: 1 }}>
                      <Text style={s.rowTitle}>{b.name}</Text>
                      <Text style={s.rowMeta} numberOfLines={1}>{b.category} · envío {money(b.default_fee ?? 0)} · {b.active_orders ?? 0} activas</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                  </Pressable>
                ))
            : couriers.data?.length === 0
              ? <EmptyState title="Aún no tienes repartidores" subtitle="Crea uno y compártele su teléfono y PIN para ingresar." />
              : couriers.data?.map((c) => (
                  <View key={c.id} testID={`courier-row-${c.id}`} style={s.row}>
                    <Avatar testID={`courier-avatar-${c.id}`} userId={c.id} name={c.name} hasPhoto={!!c.profile_photo} version={c.profile_photo} size={44} />
                    <View style={{ flex: 1 }}>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                        <View style={[s.dot, { backgroundColor: c.online ? colors.success : colors.muted }]} />
                        <Text style={s.rowTitle}>{c.name}</Text>
                      </View>
                      <Text style={s.rowMeta}>{c.phone} · {c.vehicle} · {c.active_orders ?? 0} activas</Text>
                      <Text testID={`courier-pending-${c.id}`} style={s.pending}>
                        Por pagar: {money(payMap[c.id]?.pending_total ?? 0)} ({plural(payMap[c.id]?.pending_count ?? 0, "envío", "envíos")})
                      </Text>
                      {!!payMap[c.id]?.last_paid_at && (
                        <Text style={s.rowMeta}>Último pago: {money(payMap[c.id]?.last_paid_amount ?? 0)} · {format(new Date(payMap[c.id]?.last_paid_at as string), "d MMM", { locale: es })}</Text>
                      )}
                    </View>
                    {(payMap[c.id]?.pending_count ?? 0) > 0 && (
                      <Pressable testID={`pay-courier-${c.id}`} onPress={() => setPayTarget(c)} style={s.payBtn}>
                        <Text style={s.payBtnText}>Pagar</Text>
                      </Pressable>
                    )}
                    {!user?.linked && <Pressable testID={`delete-courier-${c.id}`} onPress={() => setDel(c)} hitSlop={8} style={s.iconBtn}>
                      <Ionicons name="trash-outline" size={20} color={colors.error} />
                    </Pressable>}
                  </View>
                ))}
        </ScrollView>
      )}

      <ChangePasswordSheet visible={pwOpen} onClose={() => setPwOpen(false)} />
      <Sheet testID="business-sheet" visible={bizSheet} onClose={() => setBizSheet(false)} title="Nuevo comercio">
        <Field testID="business-name-input" label="Nombre" value={bName} onChangeText={setBName} placeholder="Ej. Pizzería Napoli" />
        <Text style={s.label}>Categoría</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
          {CATEGORIES.map((c) => <Chip key={c} testID={`business-cat-${c}`} label={c} selected={bCat === c} onPress={() => setBCat(c)} />)}
        </ScrollView>
        <AddressInput
          testID="business-address"
          label="Dirección de recogida"
          value={bAddr}
          picked={!!bPick}
          onChangeText={(t) => { setBAddr(t); setBPick(null); }}
          onPick={(p) => { setBAddr(p.address); setBPick(p); }}
        />
        <Field testID="business-phone-input" label="Teléfono" value={bPhone} onChangeText={setBPhone} keyboardType="phone-pad" />
        <Field testID="business-fee-input" label="Precio fijo del envío (€) · el comercio no lo ve" value={bFee} onChangeText={setBFee} keyboardType="decimal-pad" placeholder="Ej. 3,50" />
        <Button testID="business-save-button" title="Guardar comercio" onPress={() => addBiz.mutate()} loading={addBiz.isPending} disabled={!bName.trim()} />
      </Sheet>

      <Sheet testID="courier-sheet" visible={courierSheet} onClose={() => setCourierSheet(false)} title="Nuevo repartidor">
        <Field testID="new-courier-name-input" label="Nombre" value={cName} onChangeText={setCName} placeholder="Ej. Carlos Gómez" />
        <Field testID="new-courier-phone-input" label="Teléfono (lo usa para ingresar)" value={cPhone} onChangeText={setCPhone} keyboardType="phone-pad" />
        <Field testID="new-courier-pin-input" label="PIN de 6 dígitos" value={cPin} onChangeText={(t) => setCPin(t.replace(/\D/g, ""))} keyboardType="number-pad" maxLength={6} />
        <Text style={s.label}>Vehículo</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
          {VEHICLES.map((v) => <Chip key={v} testID={`vehicle-${v}`} label={v} selected={cVeh === v} onPress={() => setCVeh(v)} />)}
        </ScrollView>
        <Button testID="courier-save-button" title="Guardar repartidor" onPress={() => addCourier.mutate()} loading={addCourier.isPending} disabled={!cName.trim() || cPin.length !== 6 || cPhone.length < 6} />
      </Sheet>

      <Sheet testID="emergency-phones-sheet" visible={sosOpen} onClose={() => setSosOpen(false)} title="Teléfonos de emergencia">
        <Text style={s.rowMeta}>Los repartidores podrán llamar a estos números con un toque desde el botón rojo de su pantalla. Uno por línea (máximo 5).</Text>
        <PhonesEditor testID="emergency" value={sosList} onChange={setSosList} />
        <Button testID="save-emergency-phones" title="Guardar" loading={saveSos.isPending} onPress={() => saveSos.mutate()} />
      </Sheet>

      <Sheet testID="pay-courier-sheet" visible={!!payTarget} onClose={() => setPayTarget(null)} title="Pagar al repartidor">
        <Text style={s.rowTitle}>{payTarget?.name}</Text>
        <Text testID="pay-amount" style={s.payAmount}>{money(payTarget ? payMap[payTarget.id]?.pending_total ?? 0 : 0)}</Text>
        <Text style={s.rowMeta}>
          Suma de los costos de envío de {plural(payTarget ? payMap[payTarget.id]?.pending_count ?? 0 : 0, "tarea entregada", "tareas entregadas")} sin pagar. Al confirmar, quedan marcadas como pagadas y el contador vuelve a 0.
        </Text>
        <Button testID="confirm-pay-courier" title="Marcar como pagado" icon="checkmark-done" loading={pay.isPending} onPress={() => payTarget && pay.mutate(payTarget.id)} />
      </Sheet>

      <Sheet testID="delete-courier-sheet" visible={!!del} onClose={() => setDel(null)} title="Eliminar repartidor">
        <Text style={s.rowMeta}>¿Eliminar a {del?.name}? Sus entregas activas quedarán sin repartidor.</Text>
        <Button testID="confirm-delete-courier" title="Eliminar" variant="danger" loading={delCourier.isPending} onPress={() => del && delCourier.mutate(del.id)} />
      </Sheet>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: space.lg, paddingBottom: space.md, gap: space.md, borderBottomWidth: 1, borderBottomColor: c.divider },
  headRow: { flexDirection: "row", alignItems: "center" },
  title: { fontFamily: font.extrabold, fontSize: 26, color: c.onSurface, letterSpacing: -0.5 },
  sub: { fontFamily: font.medium, fontSize: 13, color: c.muted },
  logout: { flexDirection: "row", alignItems: "center", gap: 4, height: 44, paddingHorizontal: space.sm },
  logoutText: { fontFamily: font.semibold, fontSize: 14, color: c.error },
  segment: { flexDirection: "row", backgroundColor: c.surfaceTertiary, borderRadius: radius.md, padding: 4 },
  segBtn: { flex: 1, height: 40, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  segActive: { backgroundColor: c.surfaceSecondary },
  segText: { fontFamily: font.semibold, fontSize: 14, color: c.muted },
  segTextActive: { color: c.onSurface },
  list: { padding: space.lg, gap: space.md },
  row: { flexDirection: "row", alignItems: "center", gap: space.md, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, padding: space.md, minHeight: 64 },
  rowIcon: { width: 40, height: 40, borderRadius: radius.md, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  rowTitle: { fontFamily: font.bold, fontSize: 15, color: c.onSurface },
  rowMeta: { fontFamily: font.medium, fontSize: 13, color: c.muted },
  dot: { width: 8, height: 8, borderRadius: 4 },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  label: { fontFamily: font.semibold, fontSize: 13, color: c.onSurfaceTertiary },
  pending: { fontFamily: font.bold, fontSize: 13, color: c.brandPrimary, marginTop: 2 },
  payBtn: { height: 44, paddingHorizontal: space.md, borderRadius: radius.pill, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  payBtnText: { fontFamily: font.bold, fontSize: 13, color: c.onBrandPrimary },
  payAmount: { fontFamily: font.extrabold, fontSize: 34, color: c.onSurface },
}));
