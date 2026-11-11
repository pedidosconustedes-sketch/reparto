import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Business, money, Product } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Button, Chip, EmptyState, ErrorState, Field, Ionicons, Loading, Sheet, useToast } from "@/src/components/ui";
import { AddressInput, PickedAddress } from "@/src/components/AddressInput";
import { NamedPhone, PhonesEditor } from "@/src/components/PhonesEditor";
import { BizPhoto } from "@/src/components/BizPhoto";
import { font, radius, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

export default function BusinessDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [sheet, setSheet] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");

  const biz = useQuery({ queryKey: ["business", id], queryFn: () => api<Business>(`/businesses/${id}`) });
  const prods = useQuery({ queryKey: ["products", id], queryFn: () => api<Product[]>(`/products?business_id=${id}`) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["products", id] });
    qc.invalidateQueries({ queryKey: ["businesses"] });
  };

  const add = useMutation({
    mutationFn: () => api("/products", { method: "POST", body: { business_id: id, name, price: parseFloat(price.replace(",", ".")) } }),
    onSuccess: () => {
      refresh();
      setSheet(false);
      setName(""); setPrice("");
      toast("Producto agregado");
    },
    onError: (e: Error) => toast(e.message, "error"),
  });
  const toggle = useMutation({
    mutationFn: (p: Product) => api(`/products/${p.id}`, { method: "PUT", body: { available: !p.available } }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (pid: string) => api(`/products/${pid}`, { method: "DELETE" }),
    onSuccess: () => { refresh(); toast("Producto eliminado"); },
  });
  const [accOpen, setAccOpen] = useState(false);
  const [accEmail, setAccEmail] = useState("");
  const [accPass, setAccPass] = useState("");
  const [confirmAccDel, setConfirmAccDel] = useState(false);
  const saveAcc = useMutation({
    mutationFn: () => api(`/businesses/${id}/account`, { method: "PUT", body: { email: accEmail.trim(), password: accPass } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["business", id] });
      setAccOpen(false);
      setAccPass("");
      toast("Acceso del comercio guardado");
    },
    onError: (e: Error) => toast(e.message, "error"),
  });
  const delAcc = useMutation({
    mutationFn: () => api(`/businesses/${id}/account`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["business", id] });
      setAccOpen(false);
      setConfirmAccDel(false);
      toast("Acceso eliminado");
    },
  });
  const delBiz = useMutation({
    mutationFn: () => api(`/businesses/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["businesses"] });
      toast("Comercio eliminado");
      router.back();
    },
  });

  // Edit business: name, pickup address (with suggestions), phone, fixed delivery fee.
  const [editOpen, setEditOpen] = useState(false);
  const [eName, setEName] = useState("");
  const [eAddr, setEAddr] = useState("");
  const [ePhone, setEPhone] = useState("");
  const [eFee, setEFee] = useState("");
  const [ePick, setEPick] = useState<PickedAddress | null>(null);
  const [eMode, setEMode] = useState<"fixed" | "km">("fixed");
  const [eKmBase, setEKmBase] = useState("");
  const [eKmBaseKm, setEKmBaseKm] = useState("");
  const [eKmExtra, setEKmExtra] = useState("");
  const [ePhones, setEPhones] = useState<NamedPhone[]>([]);
  const num = (t: string) => parseFloat(t.replace(",", ".")) || 0;
  const str = (n?: number) => String(n ?? 0).replace(".", ",");
  const openEdit = () => {
    const b = biz.data;
    if (!b) return;
    setEName(b.name); setEAddr(b.address); setEPhone(b.phone ?? ""); setEFee(String(b.default_fee ?? 0).replace(".", ",")); setEPick(null);
    setEMode(b.pricing_mode ?? "fixed"); setEKmBase(str(b.km_base_price)); setEKmBaseKm(str(b.km_base_km)); setEKmExtra(str(b.km_extra_price));
    setEPhones(b.phones?.length ? b.phones : b.phone ? [{ name: "", phone: b.phone }] : []);
    setEditOpen(true);
  };
  const saveEdit = useMutation({
    mutationFn: () =>
      api<Business>(`/businesses/${id}`, {
        method: "PUT",
        body: {
          name: eName, category: biz.data?.category ?? "General", address: eAddr,
          phone: ePhones.find((p) => p.phone.trim())?.phone ?? ePhone, phones: ePhones.filter((p) => p.phone.trim()),
          default_fee: num(eFee), pricing_mode: eMode, km_base_price: num(eKmBase), km_base_km: num(eKmBaseKm), km_extra_price: num(eKmExtra),
          lat: ePick?.lat ?? null, lng: ePick?.lng ?? null,
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["business", id] });
      qc.invalidateQueries({ queryKey: ["businesses"] });
      setEditOpen(false);
      toast("Comercio actualizado");
    },
    onError: (e: Error) => toast(e.message, "error"),
  });

  const validPrice = !isNaN(parseFloat(price.replace(",", "."))) && parseFloat(price.replace(",", ".")) >= 0;

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <Pressable testID="back-button" onPress={() => router.back()} style={s.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        {!!biz.data && <BizPhoto businessId={biz.data.id} photo={biz.data.photo} size={44} testID="business-detail-photo" />}
        <View style={{ flex: 1 }}>
          <Text style={s.title} numberOfLines={1}>{biz.data?.name ?? "Comercio"}</Text>
          {!!biz.data && <Text style={s.sub} numberOfLines={1}>{biz.data.category}{biz.data.address ? ` · ${biz.data.address}` : ""}</Text>}
        </View>
        <Pressable testID="edit-business-button" accessibilityLabel="Editar comercio" onPress={openEdit} style={s.iconBtn}>
          <Ionicons name="create-outline" size={22} color={colors.onSurface} />
        </Pressable>
        <Pressable testID="delete-business-button" onPress={() => setConfirmDel(true)} style={s.iconBtn}>
          <Ionicons name="trash-outline" size={20} color={colors.error} />
        </Pressable>
      </View>
      {prods.isLoading ? (
        <Loading />
      ) : prods.isError ? (
        <ErrorState message="No pudimos cargar el catálogo" onRetry={() => prods.refetch()} />
      ) : (
        <ScrollView contentContainerStyle={[s.list, { paddingBottom: insets.bottom + space.xl }]}>
          {!user?.linked && <Pressable testID="business-account-row" onPress={() => { setAccEmail(biz.data?.account_email ?? ""); setAccOpen(true); }} style={s.accRow}>
            <Ionicons name="key-outline" size={20} color={colors.brandPrimary} />
            <View style={{ flex: 1 }}>
              <Text style={s.pName}>Acceso del comercio</Text>
              <Text testID="business-account-email" style={s.sub}>
                {biz.data?.account_email ? `Entra con ${biz.data.account_email}` : "Sin acceso: crea un email y contraseña para que el comercio cree pedidos"}
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={colors.muted} />
          </Pressable>}
          <Pressable testID="business-fee-row" onPress={openEdit} style={s.accRow}>
            <Ionicons name="cash-outline" size={20} color={colors.brandPrimary} />
            <View style={{ flex: 1 }}>
              <Text style={s.pName}>
                {biz.data?.pricing_mode === "km"
                  ? `Envío por km: ${money(biz.data.km_base_price ?? 0)} hasta ${biz.data.km_base_km ?? 0} km + ${money(biz.data.km_extra_price ?? 0)}/km`
                  : `Precio fijo del envío: ${money(biz.data?.default_fee ?? 0)}`}
              </Text>
              <Text style={s.sub}>Se aplica solo a los pedidos que crea el comercio. El comercio no lo ve.</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={colors.muted} />
          </Pressable>
          <View style={s.rowBetween}>
            <Text style={s.section}>Catálogo ({prods.data?.length ?? 0})</Text>
            <Button testID="add-product-button" title="Producto" icon="add" variant="secondary" onPress={() => setSheet(true)} />
          </View>
          {prods.data?.length === 0 && <EmptyState title="Sin productos" subtitle="Agrega productos con su precio para crear órdenes rápido." />}
          {prods.data?.map((p) => (
            <View key={p.id} testID={`product-row-${p.id}`} style={[s.row, !p.available && { opacity: 0.55 }]}>
              <View style={{ flex: 1 }}>
                <Text style={s.pName}>{p.name}</Text>
                <Text style={s.pPrice}>{money(p.price)}</Text>
              </View>
              <Switch
                testID={`product-available-${p.id}`}
                value={p.available}
                onValueChange={() => toggle.mutate(p)}
                trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }}
                thumbColor={colors.surfaceSecondary}
                {...({ activeThumbColor: colors.surfaceSecondary } as object)}
              />
              <Pressable testID={`delete-product-${p.id}`} onPress={() => remove.mutate(p.id)} style={s.iconBtn}>
                <Ionicons name="close-circle-outline" size={22} color={colors.muted} />
              </Pressable>
            </View>
          ))}
        </ScrollView>
      )}

      <Sheet testID="edit-business-sheet" visible={editOpen} onClose={() => setEditOpen(false)} title="Editar comercio">
        <Field testID="edit-business-name" label="Nombre" value={eName} onChangeText={setEName} />
        <AddressInput
          testID="edit-business-address"
          label="Dirección de recogida"
          value={eAddr}
          picked={!!ePick}
          onChangeText={(t) => { setEAddr(t); setEPick(null); }}
          onPick={(p) => { setEAddr(p.address); setEPick(p); }}
        />
        <Text style={s.pName}>Teléfonos del comercio</Text>
        <PhonesEditor testID="biz-phones" value={ePhones} onChange={setEPhones} />
        <Text style={s.pName}>Precio del envío</Text>
        <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap" }}>
          <Chip testID="pricing-fixed" label="Precio fijo" selected={eMode === "fixed"} onPress={() => setEMode("fixed")} />
          <Chip testID="pricing-km" label="Por kilómetros" selected={eMode === "km"} onPress={() => setEMode("km")} />
        </View>
        {eMode === "fixed" ? (
          <Field testID="edit-business-fee" label="Precio fijo del envío (€)" value={eFee} onChangeText={setEFee} keyboardType="decimal-pad" />
        ) : (
          <>
            <Field testID="km-base-price" label="Precio base (€)" value={eKmBase} onChangeText={setEKmBase} keyboardType="decimal-pad" />
            <Field testID="km-base-km" label="Incluye hasta (km)" value={eKmBaseKm} onChangeText={setEKmBaseKm} keyboardType="decimal-pad" />
            <Field testID="km-extra-price" label="Precio por km extra (€)" value={eKmExtra} onChangeText={setEKmExtra} keyboardType="decimal-pad" />
            <Text testID="km-example" style={s.sub}>
              Ej.: 5 km → {money(num(eKmBase) + Math.max(0, 5 - num(eKmBaseKm)) * num(eKmExtra))}. Se mide la ruta más corta por carretera desde la recogida hasta la entrega. Si no se puede medir, se usa el precio fijo ({money(num(eFee))}).
            </Text>
            <Field testID="edit-business-fee" label="Precio fijo de reserva (€)" value={eFee} onChangeText={setEFee} keyboardType="decimal-pad" />
          </>
        )}
        <Button testID="edit-business-save" title="Guardar" loading={saveEdit.isPending} disabled={!eName.trim()} onPress={() => saveEdit.mutate()} />
      </Sheet>
      <Sheet testID="business-account-sheet" visible={accOpen} onClose={() => setAccOpen(false)} title="Acceso del comercio">
        <Text style={s.sub}>El comercio entrará en la pestaña «Comercio» para crear pedidos y elegir repartidor. No verá la ubicación de los repartidores.</Text>
        <Field testID="business-account-email-input" label="Email" value={accEmail} onChangeText={setAccEmail} autoCapitalize="none" keyboardType="email-address" placeholder="comercio@email.com" />
        <Field testID="business-account-password-input" label={biz.data?.account_email ? "Nueva contraseña" : "Contraseña"} value={accPass} onChangeText={setAccPass} secureTextEntry placeholder="Mínimo 8 caracteres" />
        <Button testID="business-account-save" title="Guardar acceso" loading={saveAcc.isPending} disabled={!accEmail.includes("@") || accPass.length < 8} onPress={() => saveAcc.mutate()} />
        {!!biz.data?.account_email && (
          <Button testID="business-account-delete" title={confirmAccDel ? "Toca otra vez para confirmar" : "Quitar acceso"} variant={confirmAccDel ? "danger" : "ghost"} loading={delAcc.isPending} onPress={() => (confirmAccDel ? delAcc.mutate() : setConfirmAccDel(true))} />
        )}
      </Sheet>
      <Sheet testID="product-sheet" visible={sheet} onClose={() => setSheet(false)} title="Nuevo producto">
        <Field testID="product-name-input" label="Nombre" value={name} onChangeText={setName} placeholder="Ej. Pizza muzzarella" />
        <Field testID="product-price-input" label="Precio" value={price} onChangeText={setPrice} keyboardType="decimal-pad" placeholder="0.00" />
        <Button testID="product-save-button" title="Guardar producto" onPress={() => add.mutate()} loading={add.isPending} disabled={!name.trim() || !validPrice} />
      </Sheet>
      <Sheet testID="delete-business-sheet" visible={confirmDel} onClose={() => setConfirmDel(false)} title="Eliminar comercio">
        <Text style={s.sub}>Se eliminará el comercio y su catálogo. Las órdenes existentes se conservan.</Text>
        <Button testID="confirm-delete-business" title="Eliminar comercio" variant="danger" loading={delBiz.isPending} onPress={() => delBiz.mutate()} />
      </Sheet>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: space.xs, paddingHorizontal: space.sm, paddingBottom: space.md, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: font.extrabold, fontSize: 22, color: c.onSurface },
  sub: { fontFamily: font.medium, fontSize: 13, color: c.muted },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  list: { padding: space.lg, gap: space.md },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  section: { fontFamily: font.bold, fontSize: 18, color: c.onSurface },
  row: { flexDirection: "row", alignItems: "center", gap: space.sm, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, paddingLeft: space.lg, paddingVertical: space.sm },
  pName: { fontFamily: font.semibold, fontSize: 15, color: c.onSurface },
  pPrice: { fontFamily: font.bold, fontSize: 14, color: c.brandPrimary },
  accRow: { flexDirection: "row", alignItems: "center", gap: space.md, backgroundColor: c.brandTertiary, borderRadius: radius.md, padding: space.md, minHeight: 60 },
}));
