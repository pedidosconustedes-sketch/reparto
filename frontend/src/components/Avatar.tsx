import { Image } from "expo-image";
import { useEffect, useState } from "react";
import { Pressable, Text, View } from "react-native";

import { userPhotoUrl } from "@/src/api";
import { ImageViewer } from "@/src/components/ImageViewer";
import { font } from "@/src/fonts";
import { useTheme } from "@/src/theme";

type Props = { userId: string; name: string; hasPhoto?: boolean; version?: string | null; size?: number; testID?: string; zoomable?: boolean };

// Courier profile photo, falling back to initials when there's no photo. Tap to enlarge (zoomable).
export function Avatar({ userId, name, hasPhoto, version, size = 40, testID, zoomable = true }: Props) {
  const { colors } = useTheme();
  const [uri, setUri] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState(false);
  useEffect(() => {
    setFailed(false);
    if (hasPhoto) userPhotoUrl(userId, version).then(setUri).catch(() => setFailed(true));
    else setUri(null);
  }, [userId, hasPhoto, version]);
  const box = { width: size, height: size, borderRadius: size / 2 };
  if (uri && !failed) {
    const img = <Image testID={testID} source={{ uri }} style={box} contentFit="cover" transition={150} onError={() => setFailed(true)} />;
    if (!zoomable) return img;
    return (
      <>
        <Pressable testID={testID ? `${testID}-zoom` : undefined} accessibilityLabel={`Ampliar foto de ${name}`} onPress={() => setZoom(true)}>{img}</Pressable>
        <ImageViewer uri={uri} visible={zoom} onClose={() => setZoom(false)} title={name} />
      </>
    );
  }
  const initials = name.split(" ").map((w) => w[0]).filter(Boolean).slice(0, 2).join("").toUpperCase();
  return (
    <View testID={testID} style={[box, { backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }]}>
      <Text style={{ fontFamily: font.bold, fontSize: size * 0.38, color: colors.onBrandTertiary }}>{initials}</Text>
    </View>
  );
}
