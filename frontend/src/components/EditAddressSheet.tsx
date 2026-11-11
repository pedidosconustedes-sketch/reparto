import { useEffect, useState } from "react";
import { Text } from "react-native";

import { api } from "@/src/api";
import { AddressInput, PickedAddress } from "@/src/components/AddressInput";
import { Button, Sheet, useToast } from "@/src/components/ui";
import { font } from "@/src/fonts";
import { useTheme } from "@/src/theme";

type Props = { visible: boolean; onClose: () => void; path: string; current: string; onSaved: () => void };

// Admin / business corrects the delivery address, even after a courier took the order.
export function EditAddressSheet({ visible, onClose, path, current, onSaved }: Props) {
  const { colors } = useTheme();
  const toast = useToast();
  const [addr, setAddr] = useState(current);
  const [pick, setPick] = useState<PickedAddress | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (visible) {
      setAddr(current);
      setPick(null);
    }
  }, [visible, current]);
  const save = async () => {
    setBusy(true);
    try {
      await api(path, { method: "PATCH", body: { address: addr.trim(), lat: pick?.lat ?? null, lng: pick?.lng ?? null } });
      toast("Dirección actualizada; avisamos al repartidor");
      onSaved();
      onClose();
    } catch (e) {
      toast(e instanceof Error ? e.message : "No se pudo guardar", "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet testID="edit-address-sheet" visible={visible} onClose={onClose} title="Cambiar dirección de entrega">
      <AddressInput testID="edit-dest" label="Nueva dirección" value={addr} picked={!!pick}
        onChangeText={(t) => { setAddr(t); setPick(null); }} onPick={(p) => { setAddr(p.address); setPick(p); }} />
      <Text style={{ fontFamily: font.medium, fontSize: 12, color: colors.muted }}>Si el envío se cobra por km, el precio se recalcula con la nueva ruta.</Text>
      <Button testID="edit-address-save" title="Guardar dirección" loading={busy} disabled={addr.trim().length < 4} onPress={save} />
    </Sheet>
  );
}
