import { useEffect, useState } from "react";
import { Text, View } from "react-native";

import { api, Order, num } from "@/src/api";
import { Button, Chip, Field, Sheet, useToast } from "@/src/components/ui";
import { font, space } from "@/src/fonts";
import { useTheme } from "@/src/theme";

const TYPES: { key: string; label: string }[] = [
  { key: "cliente_no_localizable", label: "Cliente no localizable" },
  { key: "cliente_no_responde", label: "El cliente no responde" },
  { key: "direccion_incorrecta", label: "Dirección incorrecta" },
  { key: "pedido_no_listo", label: "El pedido no está listo" },
  { key: "cliente_rechaza", label: "El cliente rechaza el pedido" },
  { key: "otro", label: "Otra incidencia" },
];

// Courier reports a problem on a task; the admin and the business are notified.
export function IncidentSheet({ order, onClose, onSaved }: { order: Order | null; onClose: () => void; onSaved: () => void }) {
  const { colors } = useTheme();
  const toast = useToast();
  const [type, setType] = useState("cliente_no_localizable");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (order) {
      setType("cliente_no_localizable");
      setNote("");
    }
  }, [order]);
  const save = async () => {
    if (!order) return;
    setBusy(true);
    try {
      await api(`/courier/orders/${order.id}/incident`, { method: "POST", body: { type, note } });
      toast("Incidencia enviada al administrador");
      onSaved();
      onClose();
    } catch (e) {
      toast(e instanceof Error ? e.message : "No se pudo enviar", "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet testID="incident-sheet" visible={!!order} onClose={onClose} title={`Incidencia · #${order ? num(order.number) : ""}`}>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space.sm }}>
        {TYPES.map((t) => (
          <Chip key={t.key} testID={`incident-type-${t.key}`} label={t.label} selected={type === t.key} onPress={() => setType(t.key)} />
        ))}
      </View>
      <Field testID="incident-note-input" label="Comentario" value={note} onChangeText={setNote} multiline placeholder="Cuenta qué ha pasado (opcional)" maxLength={500} />
      {(order?.incidents?.length ?? 0) > 0 && (
        <Text style={{ fontFamily: font.medium, fontSize: 12, color: colors.muted }}>
          Ya enviadas: {order?.incidents?.map((i) => i.label).join(", ")}
        </Text>
      )}
      <Button testID="incident-save" title="Enviar incidencia" icon="send" loading={busy} disabled={type === "otro" && !note.trim()} onPress={save} />
    </Sheet>
  );
}
