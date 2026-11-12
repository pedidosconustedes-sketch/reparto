
 import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet } from "react-native";
import { router } from "expo-router";

export default function LoginScreen() {
  const [mode, setMode] = useState<"owner" | "register" | "courier">("owner");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
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
      let bodyData: any = {};

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
        localStorage.setItem("token", data.token);
      }

      router.replace("/");
    } catch (e: any) {
      console.error("Error capturado:", e);
      setError(e?.message || "Error al ingresar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1, padding: 20, justifyContent: "center", maxWidth: 400, alignSelf: "center", width: "100%" }}>
      <Text style={{ fontSize: 24, fontWeight: "bold", marginBottom: 20, textAlign: "center" }}>Reparto</Text>
      
      <View style={{ flexDirection: "row", marginBottom: 20, justifyContent: "center" }}>
        <TouchableOpacity onPress={() => setMode("owner")} style={{ padding: 10, borderBottomWidth: mode === "owner" ? 2 : 0, borderColor: "green" }}>
          <Text>Admin / Comercio</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => setMode("register")} style={{ padding: 10, borderBottomWidth: mode === "register" ? 2 : 0, borderColor: "green" }}>
          <Text>Registrarse</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => setMode("courier")} style={{ padding: 10, borderBottomWidth: mode === "courier" ? 2 : 0, borderColor: "green" }}>
          <Text>Repartidor</Text>
        </TouchableOpacity>
      </View>

      {error ? <Text style={{ color: "red", marginBottom: 10, textAlign: "center" }}>{error}</Text> : null}

      {mode === "register" && (
        <TextInput
          placeholder="Nombre"
          value={name}
          onChangeText={setName}
          style={{ borderWidth: 1, borderColor: "#ccc", padding: 10, marginBottom: 10, borderRadius: 5 }}
        />
      )}

      {mode !== "courier" ? (
        <>
          <TextInput
            placeholder="Correo electrónico"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            style={{ borderWidth: 1, borderColor: "#ccc", padding: 10, marginBottom: 10, borderRadius: 5 }}
          />
          <TextInput
            placeholder="Contraseña"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            style={{ borderWidth: 1, borderColor: "#ccc", padding: 10, marginBottom: 15, borderRadius: 5 }}
          />
        </>
      ) : (
        <>
          <TextInput
            placeholder="Teléfono"
            value={phone}
            onChangeText={setPhone}
            style={{ borderWidth: 1, borderColor: "#ccc", padding: 10, marginBottom: 10, borderRadius: 5 }}
          />
          <TextInput
            placeholder="PIN"
            value={pin}
            onChangeText={setPin}
            secureTextEntry
            style={{ borderWidth: 1, borderColor: "#ccc", padding: 10, marginBottom: 15, borderRadius: 5 }}
          />
        </>
      )}

      <TouchableOpacity
        onPress={submit}
        disabled={busy}
        style={{ backgroundColor: "#28a745", padding: 12, borderRadius: 5, alignItems: "center" }}
      >
        <Text style={{ color: "#fff", fontWeight: "bold" }}>{busy ? "Procesando..." : "Continuar"}</Text>
      </TouchableOpacity>
    </View>
  );
}
