import * as Location from "expo-location";
import * as TaskManager from "expo-task-manager";
import { Platform } from "react-native";

import { api } from "@/src/api";

export const BG_TASK = "courier-bg-location";

// Defined at module scope so the OS can wake it while the app is closed (published build only).
if (Platform.OS !== "web") {
  TaskManager.defineTask<{ locations: Location.LocationObject[] }>(BG_TASK, async ({ data, error }) => {
    if (error || !data?.locations?.length) return;
    const p = data.locations[data.locations.length - 1];
    await api("/courier/location", { method: "POST", body: { lat: p.coords.latitude, lng: p.coords.longitude } }).catch(() => {});
  });
}

export async function startBackgroundLocation(): Promise<boolean> {
  if (Platform.OS === "web") return false;
  try {
    const bg = await Location.getBackgroundPermissionsAsync();
    if (!bg.granted) return false;
    if (await Location.hasStartedLocationUpdatesAsync(BG_TASK)) return true;
    await Location.startLocationUpdatesAsync(BG_TASK, {
      accuracy: Location.Accuracy.Balanced,
      timeInterval: 20000,
      distanceInterval: 40,
      showsBackgroundLocationIndicator: true,
      pausesUpdatesAutomatically: false,
      foregroundService: {
        notificationTitle: "Reparto: compartiendo ubicación",
        notificationBody: "El administrador ve dónde estás mientras estás en línea",
      },
    });
    return true;
  } catch {
    return false; // Not available in Expo Go
  }
}

export async function stopBackgroundLocation() {
  if (Platform.OS === "web") return;
  try {
    if (await Location.hasStartedLocationUpdatesAsync(BG_TASK)) await Location.stopLocationUpdatesAsync(BG_TASK);
  } catch {
    // ignore
  }
}
