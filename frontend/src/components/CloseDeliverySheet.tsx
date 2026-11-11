import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { useEffect, useState } from "react";
import { Linking, Pressable, Text, View } from "react-native";

import { api, BASE, money, Order, TOKEN_KEY, num } from "@/src/api";
import { Button, Field, Ionicons, Sheet, useToast } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { PAYMENT_ICON, PAYMENT_LABEL } from "@/src/status";
import { makeStyles, useTheme } from "@/src/theme";
import { uploadForm } from "@/src/utils/upload";
import { storage } from "@/src/utils/storage";

type Props = { order: Order | null; onClose: () => void; onDone: (o: Order) => void };

export function CloseDeliverySheet({ order, onClose, onDone }: Props) {
  const s = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const [photo, setPhoto] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [camBlocked, setCamBlocked] = useState(false);

  useEffect(() => {
    if (order) {
      setPhoto(null);
      setNote("");
    }
  }, [order]);

  const takePhoto = async () => {
    let p = await ImagePicker.getCameraPermissionsAsync();
    if (!p.granted && p.canAskAgain) p = await ImagePicker.requestCameraPermissionsAsync();
    if (!p.granted) {
      setCamBlocked(!p.canAskAgain);
      if (p.canAskAgain) toast("Necesitamos la cámara para la foto de entrega", "error");
      return;
    }
    setCamBlocked(false);
    const r = await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], quality: 0.4, base64: true });
    if (!r.canceled) setPhoto(r.assets[0]);
  };

  const confirm = async () => {
    if (!order) return;
    setBusy(true);
    try {
      if (photo) {
        const token = await storage.secureGet<string | null>(TOKEN_KEY, null);
        let ok = false;
        try {
          const res = await uploadForm(`${BASE}/courier/orders/${order.id}/photo`, {
            headers: { Authorization: `Bearer ${token}` },
            files: { file: { uri: photo.uri, name: photo.fileName ?? "entrega.jpg", mimeType: photo.mimeType ?? "image/jpeg" } },
          });
          ok = res.ok;
        } catch {
          ok = false;
        }
        // Backup path: send the photo as base64 if the file upload failed or arrived empty.
        if (!ok) {
          if (!photo.base64) throw new Error("No se pudo subir la foto, vuelve a tomarla");
          await api(`/courier/orders/${order.id}/photo-b64`, { method: "POST", body: { data: photo.base64, mime: photo.mimeType ?? "image/jpeg" } });
        }
      }
      const o = await api<Order>(`/courier/orders/${order.id}/status`, { method: "PATCH", body: { status: "entregado", note } });
      onDone(o);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Error al cerrar la entrega", "error");
    } finally {
      setBusy(false);
    }
  };

  const pm = order?.payment_method ?? "efectivo";

  return (
    <Sheet testID="close-delivery-sheet" visible={!!order} onClose={onClose} title={`Cerrar entrega #${order ? num(order.number) : ""}`}>
      <View style={s.payRow}>
        <Ionicons name={PAYMENT_ICON[pm]} size={20} color={colors.onBrandTertiary} />
        <Text testID="close-payment-label" style={s.payText}>
          {pm === "pagado" ? "Ya pagado: no cobrar" : `Cobrar ${money(order?.total ?? 0)} con ${PAYMENT_LABEL[pm].toLowerCase()}`}
        </Text>
      </View>

      <Text style={s.label}>Foto de la entrega (opcional)</Text>
      {photo ? (
        <View>
          <Image testID="close-photo-preview" source={{ uri: photo.uri }} style={s.preview} contentFit="cover" />
          <Pressable testID="retake-photo-button" onPress={takePhoto} style={s.retake}>
            <Ionicons name="camera-reverse-outline" size={18} color={colors.onSurfaceInverse} />
            <Text style={s.retakeText}>Repetir</Text>
          </Pressable>
        </View>
      ) : (
        <Pressable testID="take-photo-button" onPress={takePhoto} style={s.photoBox}>
          <Ionicons name="camera-outline" size={30} color={colors.brandPrimary} />
          <Text style={s.photoTitle}>Tomar foto</Text>
          <Text style={s.photoSub}>Sirve como comprobante para el comercio</Text>
        </Pressable>
      )}
      {camBlocked && (
        <View style={s.blocked}>
          <Text style={s.blockedText}>El acceso a la cámara está desactivado. Actívalo en los ajustes para tomar la foto.</Text>
          <Button testID="camera-settings-button" title="Abrir ajustes" icon="settings-outline" variant="ghost" onPress={() => Linking.openSettings()} />
        </View>
      )}

      <Field testID="delivery-note-input" label="Nota (opcional)" value={note} onChangeText={setNote} placeholder="Ej. Entregado al portero" multiline maxLength={500} />
      <Button testID="confirm-delivery-button" title="Confirmar entrega" icon="checkmark-done" size="lg" loading={busy} onPress={confirm} />
    </Sheet>
  );
}

const useStyles = makeStyles((c) => ({
  payRow: { flexDirection: "row", alignItems: "center", gap: space.sm, backgroundColor: c.brandTertiary, borderRadius: radius.md, padding: space.md },
  payText: { fontFamily: font.bold, fontSize: 15, color: c.onBrandTertiary, flex: 1 },
  label: { fontFamily: font.semibold, fontSize: 13, color: c.onSurfaceTertiary },
  photoBox: { height: 140, borderRadius: radius.md, borderWidth: 1.5, borderStyle: "dashed", borderColor: c.borderStrong, alignItems: "center", justifyContent: "center", gap: 4 },
  photoTitle: { fontFamily: font.bold, fontSize: 15, color: c.brandPrimary },
  photoSub: { fontFamily: font.medium, fontSize: 12, color: c.muted },
  preview: { width: "100%", height: 200, borderRadius: radius.md },
  retake: { position: "absolute", right: space.sm, bottom: space.sm, flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: c.surfaceInverse, borderRadius: radius.pill, paddingHorizontal: space.md, height: 36 },
  retakeText: { fontFamily: font.bold, fontSize: 13, color: c.onSurfaceInverse },
  blocked: { gap: space.sm },
  blockedText: { fontFamily: font.semibold, fontSize: 13, color: c.error },
}));
