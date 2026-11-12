import React from "react";
import { Redirect } from "expo-router";
import { useAuth } from "@/src/auth";
import { View, ActivityIndicator, Text } from "react-native";

export default function Index() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
        <ActivityIndicator size="large" color="#28a745" />
        <Text style={{ marginTop: 10 }}>Cargando Reparto...</Text>
      </View>
    );
  }

  if (!user) {
    return <Redirect href="/login" />;
  }

  const role = user.role || "courier";
  if (role === "owner") {
    return <Redirect href="/(owner)" />;
  } else if (role === "business") {
    return <Redirect href="/biz" />;
  } else {
    return <Redirect href="/courier" />;
  }
}
