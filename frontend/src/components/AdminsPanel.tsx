import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Pressable, Text, View } from "react-native";

import { api, User } from "@/src/api";
import { Button, Chip, Field, Ionicons, Sheet, useToast } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

// Main admin only: create/delete secondary admins, linked to the main account or fully independent.
export function AdminsPanel() {
  const s = useStyles();
  const { colors } = useTheme();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["admins"], queryFn: () => api<User[]>("/admins") });
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [pass, setPass] = useState("");
  const [linked, setLinked] = useState(true);
  const [confirm, setConfirm] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: () => api<User>("/admins", { method: "POST", body: { name, email: email.trim(), password: pass, linked } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admins"] });
      setOpen(false);
      setName(""); setEmail(""); setPass(""); setLinked(true);
      toast("Administrador creado");
    },
    onError: (e: Error) => toast(e.message, "error"),
  });
  const del = useMutation({
    mutationFn: (id: string) => api(`/admins/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admins"] });
      setConfirm(null);
      toast("Administrador eliminado");
    },
  });
  return (
    <View style={{ gap: space.md }}>
      <Button testID="add-admin-button" title="Agregar administrador" icon="add" variant="secondary" onPress={() => setOpen(true)} />
      {(q.data ?? []).length === 0 && <Text style={s.meta}>Aún no hay administradores secundarios.</Text>}
      {(q.data ?? []).map((a) => (
        <View key={a.id} testID={`admin-row-${a.id}`} style={s.row}>
          <Ionicons name={a.linked ? "link-outline" : "briefcase-outline"} size={22} color={colors.brandPrimary} />
          <View style={{ flex: 1 }}>
            <Text style={s.name}>{a.name}</Text>
            <Text style={s.meta} numberOfLines={1}>{a.email}</Text>
            <Text style={s.meta}>{a.linked ? "Vinculado: gestiona tu cuenta" : "Independiente: sus propios comercios y repartidores"}</Text>
          </View>
          <Pressable testID={`delete-admin-${a.id}`} onPress={() => (confirm === a.id ? del.mutate(a.id) : setConfirm(a.id))} style={s.del}>
            <Text style={[s.delText, confirm === a.id && { color: colors.error }]}>{confirm === a.id ? "¿Seguro?" : "Borrar"}</Text>
          </Pressable>
        </View>
      ))}
      <Sheet testID="admin-sheet" visible={open} onClose={() => setOpen(false)} title="Nuevo administrador">
        <Field testID="admin-name-input" label="Nombre" value={name} onChangeText={setName} />
        <Field testID="admin-email-input" label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" />
        <Field testID="admin-password-input" label="Contraseña" value={pass} onChangeText={setPass} secureTextEntry placeholder="Mínimo 8 caracteres" />
        <Text style={s.name}>Tipo de cuenta</Text>
        <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap" }}>
          <Chip testID="admin-linked" label="Vinculada a mi cuenta" selected={linked} onPress={() => setLinked(true)} />
          <Chip testID="admin-independent" label="Independiente" selected={!linked} onPress={() => setLinked(false)} />
        </View>
        <Text style={s.meta}>
          {linked
            ? "Ve y gestiona tus pedidos, comercios, repartidores y dinero, pero no puede crear cuentas."
            : "Empieza desde cero: crea sus propios comercios, repartidores y precios. No ve nada de tu cuenta y tú no ves lo suyo."}
        </Text>
        <Button testID="admin-save" title="Crear administrador" loading={add.isPending} disabled={!name.trim() || !email.includes("@") || pass.length < 8} onPress={() => add.mutate()} />
      </Sheet>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  row: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.md, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary },
  name: { fontFamily: font.bold, fontSize: 15, color: c.onSurface },
  meta: { fontFamily: font.medium, fontSize: 12, color: c.muted },
  del: { minWidth: 64, height: 44, alignItems: "center", justifyContent: "center" },
  delText: { fontFamily: font.bold, fontSize: 13, color: c.muted },
}));
