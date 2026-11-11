import { Image, ImageStyle } from "expo-image";
import { useEffect, useState } from "react";
import { Pressable, StyleProp, Text, View } from "react-native";

import { photoUrl } from "@/src/api";
import { ImageViewer } from "@/src/components/ImageViewer";
import { Ionicons } from "@/src/components/ui";
import { font } from "@/src/fonts";
import { useTheme } from "@/src/theme";

export function DeliveryPhoto({ orderId, style }: { orderId: string; style?: StyleProp<ImageStyle> }) {
  const { colors } = useTheme();
  const [uri, setUri] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState(false);
  useEffect(() => {
    setFailed(false);
    photoUrl(orderId).then(setUri).catch(() => setFailed(true));
  }, [orderId]);
  if (failed) {
    return (
      <View testID="delivery-photo-missing" style={[{ backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center", gap: 6 }, style as object]}>
        <Ionicons name="image-outline" size={28} color={colors.muted} />
        <Text style={{ fontFamily: font.semibold, fontSize: 13, color: colors.muted, textAlign: "center", paddingHorizontal: 16 }}>
          La foto de esta entrega no se pudo guardar
        </Text>
      </View>
    );
  }
  if (!uri) return <View style={[{ backgroundColor: colors.surfaceTertiary }, style as object]} />;
  return (
    <>
      <Pressable testID="delivery-photo-zoom" accessibilityLabel="Ampliar foto" onPress={() => setZoom(true)}>
        <Image
          testID="delivery-photo"
          source={{ uri }}
          style={style}
          contentFit="cover"
          transition={200}
          cachePolicy="none"
          onError={() => setFailed(true)}
        />
      </Pressable>
      <ImageViewer uri={uri} visible={zoom} onClose={() => setZoom(false)} title="Foto de entrega" />
    </>
  );
}
