import { useState } from "react";
import { Text } from "react-native";

import { api, TOKEN_KEY } from "@/src/api";
import { Button, Field, Sheet, useToast } from "@/src/components/ui";
import { font } from "@/src/fonts";
import { useTheme } from "@/src/theme";
import { storage } from "@/src/utils/storage";

type Props = { visible: boolean; onClose: () => void };

// Owner / business change their own password. Other devices get signed out.
export function ChangePasswordSheet({ visible, onClose }: Props) {
  const { colors } = useTheme();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const save = async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await api<{ token: string }>("/auth/change-password", { method: "POST", body: { current_password: current, new_password: next } });
      await storage.secureSet(TOKEN_KEY, r.token);
      setCurrent("");
      setNext("");
      toast("Contraseña cambiada");
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "No se pudo cambiar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet testID="change-password-sheet" visible={visible} onClose={onClose} title="Cambiar contraseña">
      <Text style={{ fontFamily: font.medium, fontSize: 14, color: colors.muted }}>
        Se cerrará la sesión en los demás dispositivos.
      </Text>
      <Field testID="current-password-input" label="Contraseña actual" value={current} onChangeText={setCurrent} secureTextEntry />
      <Field testID="new-password-input" label="Nueva contraseña" value={next} onChangeText={setNext} secureTextEntry placeholder="Mínimo 8 caracteres" />
      {!!err && <Text testID="change-password-error" style={{ fontFamily: font.semibold, fontSize: 13, color: colors.error }}>{err}</Text>}
      <Button testID="change-password-save" title="Guardar" loading={busy} disabled={!current || next.length < 8} onPress={save} />
    </Sheet>
  );
}
