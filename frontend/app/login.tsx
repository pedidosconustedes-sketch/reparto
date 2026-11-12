import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAuth } from "@/src/auth";
import { Button, Field, Ionicons } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { makeStyles, useTheme } from "@/src/theme";

type Mode = "owner" | "business" | "courier" | "register";

export default function Login() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { signIn } = useAuth();
  const [mode, setMode] = useState<Mode>("owner");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

const submit = async () => {
  console.log("¡Se ha pulsado el botón de enviar!");
  setError("");
  setBusy(true);
  try {
    let endpoint = "";
    let bodyData = {};

    if (mode === "owner") {
      endpoint = "/auth/login";
      bodyData = { email: email.trim(), password };
    } else if (mode === "register") {
      endpoint = "/auth/register";
      bodyData = { name, email: email.trim(), password, phone };
    } else {
      endpoint = "/auth/courier/login";
      bodyData = { phone, pin };
    }

    const res = await fetch(https://reparto-app.onrender.com${endpoint}, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bodyData),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || "Error en el servidor");
    }

    if (data.token) {
      await storage.secureSet(TOKEN_KEY, data.token);
    }

    router.replace("/");
  } catch (e: any) {
    console.error("Error capturado:", e);
    setError(e?.message || "Error al ingresar");
  } finally {
    setBusy(false);
  }
};

  const tabs: { key: Mode; label: string }[] = [
  { key: "owner", label: "Admin" },
  { key: "business", label: "Comercio" },
  { key: "courier", label: "Repartidor" },
  { key: "register", label: "Registrarse" },
];

  return (
    <View style={s.root}>
      <KeyboardAwareScrollView
        bottomOffset={24}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={[s.content, { paddingTop: insets.top + space.xxl, paddingBottom: insets.bottom + space.xl }]}
      >
        <View style={s.logo}>
          <Ionicons name="bicycle" size={30} color={colors.onBrandPrimary} />
        </View>
        <Text style={s.title}>Reparto</Text>
        <Text style={s.subtitle}>Gestiona los pedidos y repartidores de todos tus comercios.</Text>

        <View style={s.segment}>
          {tabs.map((t) => {
            const active = mode === t.key || (t.key === "owner" && mode === "register");
            return (
              <Pressable
                key={t.key}
                testID={`login-tab-${t.key}`}
                onPress={() => {
                  setMode(t.key);
                  setError("");
                }}
                style={[s.segBtn, active && s.segActive]}
              >
                <Text style={[s.segText, active && s.segTextActive]}>{t.label}</Text>
              </Pressable>
            );
          })}
        </View>

        <View style={s.form}>
          {mode === "register" && <Field testID="register-name-input" label="Tu nombre" value={name} onChangeText={setName} placeholder="Ej. Laura Méndez" />}
          {mode !== "courier" ? (
            <>
              <Field testID="login-email-input" label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="tu@email.com" />
              <Field testID="login-password-input" label="Contraseña" value={password} onChangeText={setPassword} secureTextEntry placeholder={mode === "register" ? "Mínimo 8 caracteres" : "••••••••"} />
            </>
          ) : (
            <>
              <Field testID="courier-phone-input" label="Teléfono" value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="1100000001" />
              <Field testID="courier-pin-input" label="PIN de 6 dígitos" value={pin} onChangeText={setPin} keyboardType="number-pad" maxLength={6} secureTextEntry placeholder="••••••" />
            </>
          )}
          {!!error && <Text testID="login-error" style={s.error}>{error}</Text>}
          <Button testID="login-submit-button" title={mode === "register" ? "Crear cuenta" : "Ingresar"} onPress={submit} loading={busy} size="lg" />
          {mode === "owner" && (
            <Text style={s.hint}>Las cuentas nuevas las crea el administrador.</Text>
          )}
          {mode === "business" && <Text style={s.hint}>El email y la contraseña de tu comercio te los da el administrador.</Text>}
          {mode === "register" && (
            <Pressable testID="go-login-button" onPress={() => setMode("owner")} style={s.link}>
              <Text style={s.linkText}>Ya tengo cuenta</Text>
            </Pressable>
          )}
          {mode === "courier" && <Text style={s.hint}>Tu teléfono y PIN te los da el propietario del comercio.</Text>}
        </View>
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  content: { paddingHorizontal: space.xl, gap: space.sm },
  logo: { width: 56, height: 56, borderRadius: radius.lg, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center", marginBottom: space.md },
  title: { fontFamily: font.extrabold, fontSize: 32, color: c.onSurface, letterSpacing: -0.5 },
  subtitle: { fontFamily: font.regular, fontSize: 15, color: c.muted, lineHeight: 22 },
  segment: { flexDirection: "row", backgroundColor: c.surfaceTertiary, borderRadius: radius.md, padding: 4, marginTop: space.xl },
  segBtn: { flex: 1, height: 44, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  segActive: { backgroundColor: c.surfaceSecondary, shadowColor: c.onSurface, shadowOpacity: 0.06, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 1 },
  segText: { fontFamily: font.semibold, fontSize: 14, color: c.muted },
  segTextActive: { color: c.onSurface },
  form: { gap: space.lg, marginTop: space.xl },
  error: { fontFamily: font.semibold, fontSize: 13, color: c.error },
  link: { alignItems: "center", paddingVertical: space.sm, minHeight: 44, justifyContent: "center" },
  linkText: { fontFamily: font.semibold, fontSize: 14, color: c.brandPrimary },
  hint: { fontFamily: font.regular, fontSize: 13, color: c.muted, textAlign: "center" },
}));
