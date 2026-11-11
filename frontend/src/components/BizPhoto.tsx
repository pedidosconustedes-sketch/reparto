import { Image } from "expo-image";
import { useEffect, useState } from "react";
import { Pressable, View } from "react-native";

import { businessPhotoUrl } from "@/src/api";
import { ImageViewer } from "@/src/components/ImageViewer";
import { Ionicons } from "@/src/components/ui";
import { useTheme } from "@/src/theme";

type Props = { businessId: string; photo?: string | null; size?: number; testID?: string; tryAlways?: boolean; zoomable?: boolean; title?: string };

// Business (comercio) photo with a storefront icon fallback. Tap to enlarge.
export function BizPhoto({ businessId, photo, size = 44, testID, tryAlways, zoomable = true, title }: Props) {
  const { colors } = useTheme();
  const [uri, setUri] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState(false);
  useEffect(() => {
    setFailed(false);
    if (photo || tryAlways) businessPhotoUrl(businessId, photo).then(setUri).catch(() => setFailed(true));
    else setUri(null);
  }, [businessId, photo, tryAlways]);
  const box = { width: size, height: size, borderRadius: size * 0.25 };
  if (uri && !failed) {
    const img = <Image testID={testID} source={{ uri }} style={box} contentFit="cover" transition={150} onError={() => setFailed(true)} />;
    if (!zoomable) return img;
    return (
      <>
        <Pressable testID={testID ? `${testID}-zoom` : undefined} accessibilityLabel="Ampliar foto del comercio" onPress={() => setZoom(true)}>{img}</Pressable>
        <ImageViewer uri={uri} visible={zoom} onClose={() => setZoom(false)} title={title ?? "Comercio"} />
      </>
    );
  }
  return (
    <View testID={testID} style={[box, { backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" }]}>
      <Ionicons name="storefront" size={size * 0.5} color={colors.onBrandPrimary} />
    </View>
  );
}
