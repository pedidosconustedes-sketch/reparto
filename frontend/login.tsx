import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity } from "react-native";
import { router } from "expo-router";

export default function LoginScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError("");
    setBusy(true);
    try {
      const res = await fetch("https://reparto-app.onrender.com/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Error al ingresar");

      if (data.token) {
        localStorage.setItem("token", data.token);
      }

      router.replace("/");
    } catch (e: any) {
      setError(e?.message || "Error al ingresar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1, padding: 20, justifyContent: "center", maxWidth: 400, alignSelf: "center", width: "100%" }}>
      <Text style={{ fontSize: 24, fontWeight: "bold", marginBottom: 20, textAlign: "center" }}>Reparto</Text>
      
      {error ? <Text style={{ color: "red", marginBottom: 10, textAlign: "center" }}>{error}</Text> : null}

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

      <TouchableOpacity
        onPress={submit}
        disabled={busy}
        style={{ backgroundColor: "#28a745", padding: 12, borderRadius: 5, alignItems: "center" }}
      >
        <Text style={{ color: "#fff", fontWeight: "bold" }}>{busy ? "Procesando..." : "Ingresar"}</Text>
      </TouchableOpacity>
    </View>
  );
}
