import { createAudioPlayer, setAudioModeAsync } from "expo-audio";
import { Platform, Vibration } from "react-native";

let player: ReturnType<typeof createAudioPlayer> | null = null;

// Plays the alert sound and vibrates the phone (works while the app is open).
export async function ring() {
  try {
    if (!player) {
      await setAudioModeAsync({ playsInSilentMode: true });
      player = createAudioPlayer(require("../assets/sounds/alert.wav"));
    }
    await player.seekTo(0);
    player.play();
  } catch {
    // Web may block audio until the user interacts with the page.
  }
  if (Platform.OS !== "web") Vibration.vibrate([0, 500, 250, 500, 250, 500]);
}
