import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { api } from "@/src/api";

// Registers this phone for real push notifications (only works in a published build, not Expo Go / web).
export async function registerForPush() {
  if (Platform.OS === "web" || !Device.isDevice) return;
  try {
    const { status } = await Notifications.requestPermissionsAsync();
    if (status !== "granted") return;
    const tokenResp = await Notifications.getDevicePushTokenAsync();
    await api("/register-push", { method: "POST", body: { platform: Platform.OS, device_token: String(tokenResp.data) } });
  } catch {
    // Expo Go or missing push config: the in-app alert sound still works.
  }
}
