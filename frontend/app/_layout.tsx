import { QueryClientProvider } from "@tanstack/react-query";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useFonts } from "expo-font";
import * as Linking from "expo-linking";
import * as Notifications from "expo-notifications";
import { Stack, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { LogBox, Platform, StyleSheet, Text } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";

import { AuthProvider } from "@/src/auth";
import "@/src/bgLocation";
import { ErrorBoundary } from "@/src/components/error-boundary";
import { Button, Sheet, ToastProvider } from "@/src/components/ui";
import { fontAssets } from "@/src/fonts";
import { queryClient } from "@/src/query-client";
import { useTheme } from "@/src/theme";

// Disable logbox errors etc so that users can see the app
// and agent works as expected.
LogBox.ignoreAllLogs(true)

// Push notifications: foreground display + Android channel (module scope, native only).
if (Platform.OS !== "web") {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });
}
if (Platform.OS === "android") {
  Notifications.setNotificationChannelAsync("default", {
    name: "Pedidos",
    importance: Notifications.AndroidImportance.MAX,
    sound: "default",
    vibrationPattern: [0, 500, 250, 500],
  });
}

function usePushHandlers() {
  const router = useRouter();
  const [nudge, setNudge] = useState(false);
  useEffect(() => {
    if (Platform.OS === "web") return;
    const open = (data: Record<string, unknown>) => {
      const url = (data.deeplink || data.action_url) as string | undefined;
      if (!url) return;
      if (url.startsWith("http")) Linking.openURL(url);
      else router.push(url as never);
    };
    const tapSub = Notifications.addNotificationResponseReceivedListener((r) => open(r.notification.request.content.data || {}));
    Notifications.getLastNotificationResponseAsync().then((r) => {
      if (r) open(r.notification.request.content.data || {});
    });
    (async () => {
      const { status, canAskAgain } = await Notifications.getPermissionsAsync();
      if (status !== "denied" || canAskAgain) return;
      const last = await AsyncStorage.getItem("pushNudgeAt");
      if (last && Date.now() - Number(last) <= 7 * 24 * 60 * 60 * 1000) return;
      setNudge(true);
    })();
    return () => tapSub.remove();
  }, [router]);
  const close = async (settings: boolean) => {
    await AsyncStorage.setItem("pushNudgeAt", String(Date.now()));
    setNudge(false);
    if (settings) Linking.openSettings();
  };
  return { nudge, close };
}

function PushNudge() {
  const { nudge, close } = usePushHandlers();
  const { colors } = useTheme();
  return (
    <Sheet testID="push-nudge-sheet" visible={nudge} onClose={() => close(false)} title="Activa las notificaciones">
      <Text style={[styles.nudge, { color: colors.onSurfaceTertiary }]}>Sin notificaciones no te avisaremos de nuevas tareas cuando la app esté cerrada.</Text>
      <Button testID="push-open-settings" title="Abrir ajustes" icon="settings-outline" onPress={() => close(true)} />
      <Button testID="push-later" title="Más tarde" variant="ghost" onPress={() => close(false)} />
    </Sheet>
  );
}

export default function RootLayout() {
  const [loaded, error] = useFonts(fontAssets);
  const { colors } = useTheme();
  if (!loaded && !error) return null;
  // One app level ErrorBoundary; a render crash shows a reload screen
  // instead of a blank app. GestureHandlerRootView must wrap the whole tree
  // or any gesture/swipe/drawer screen crashes in Expo Go.
  return (
    <GestureHandlerRootView style={styles.root}>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <KeyboardProvider>
            <AuthProvider>
              <ToastProvider>
                <StatusBar style="dark" />
                <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }} />
                <PushNudge />
              </ToastProvider>
            </AuthProvider>
          </KeyboardProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  nudge: { fontSize: 15, lineHeight: 22 },
});
