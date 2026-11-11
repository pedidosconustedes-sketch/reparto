import { Image } from "expo-image";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { Gesture, GestureDetector, GestureHandlerRootView } from "react-native-gesture-handler";
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Ionicons } from "@/src/components/ui";

type Props = { uri: string | null; visible: boolean; onClose: () => void; title?: string };

// Full-screen photo: pinch to zoom, drag to move, double tap to zoom in/out.
export function ImageViewer({ uri, visible, onClose, title }: Props) {
  const insets = useSafeAreaInsets();
  const scale = useSharedValue(1);
  const saved = useSharedValue(1);
  const tx = useSharedValue(0);
  const ty = useSharedValue(0);
  const sx = useSharedValue(0);
  const sy = useSharedValue(0);

  const reset = () => {
    scale.value = withTiming(1);
    saved.value = 1;
    tx.value = withTiming(0);
    ty.value = withTiming(0);
    sx.value = 0;
    sy.value = 0;
  };
  const pinch = Gesture.Pinch()
    .onUpdate((e) => {
      scale.value = Math.min(6, Math.max(1, saved.value * e.scale));
    })
    .onEnd(() => {
      saved.value = scale.value;
    });
  const pan = Gesture.Pan()
    .onUpdate((e) => {
      if (scale.value > 1) {
        tx.value = sx.value + e.translationX;
        ty.value = sy.value + e.translationY;
      }
    })
    .onEnd(() => {
      sx.value = tx.value;
      sy.value = ty.value;
    });
  const doubleTap = Gesture.Tap()
    .numberOfTaps(2)
    .onEnd(() => {
      const next = scale.value > 1 ? 1 : 2.5;
      scale.value = withTiming(next);
      saved.value = next;
      if (next === 1) {
        tx.value = withTiming(0);
        ty.value = withTiming(0);
        sx.value = 0;
        sy.value = 0;
      }
    });
  const style = useAnimatedStyle(() => ({ transform: [{ translateX: tx.value }, { translateY: ty.value }, { scale: scale.value }] }));

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={() => { reset(); onClose(); }} statusBarTranslucent>
      <GestureHandlerRootView style={st.root}>
        <GestureDetector gesture={Gesture.Simultaneous(pinch, pan, doubleTap)}>
          <Animated.View style={[st.fill, style]}>
            {!!uri && <Image testID="image-viewer-image" source={{ uri }} style={st.fill} contentFit="contain" />}
          </Animated.View>
        </GestureDetector>
        <View style={[st.top, { paddingTop: insets.top + 8 }]}>
          <Text style={st.title} numberOfLines={1}>{title ?? ""}</Text>
          <Pressable testID="image-viewer-close" accessibilityLabel="Cerrar" onPress={() => { reset(); onClose(); }} style={st.close}>
            <Ionicons name="close" size={28} color="#FFFFFF" />
          </Pressable>
        </View>
        <Text style={[st.hint, { bottom: insets.bottom + 16 }]}>Pellizca para ampliar · doble toque para acercar</Text>
      </GestureHandlerRootView>
    </Modal>
  );
}

// Photo viewer is always on a black backdrop in both themes, so literal colors are intentional here.
const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#000000" },
  fill: { flex: 1, width: "100%" },
  top: { position: "absolute", top: 0, left: 0, right: 0, flexDirection: "row", alignItems: "center", paddingHorizontal: 16 },
  title: { flex: 1, color: "#FFFFFF", fontSize: 16, fontWeight: "700" },
  close: { width: 48, height: 48, alignItems: "center", justifyContent: "center" },
  hint: { position: "absolute", alignSelf: "center", color: "#FFFFFFAA", fontSize: 12 },
});
