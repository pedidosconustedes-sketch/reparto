import { Ionicons } from "@react-native-vector-icons/ionicons";
import { Image } from "expo-image";
import * as Haptics from "expo-haptics";
import { createContext, ReactNode, useCallback, useContext, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from "react-native";
import Animated, { FadeInUp, FadeOutUp } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { OrderStatus } from "@/src/api";
import { font, radius, space } from "@/src/fonts";
import { STATUS_LABEL, statusColor } from "@/src/status";
import { makeStyles, useTheme } from "@/src/theme";

export { Ionicons };
export type IconName = React.ComponentProps<typeof Ionicons>["name"];

export const tap = () => {
  if (Platform.OS !== "web") Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
};

// ---------- Button ----------
type BtnProps = {
  title: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  loading?: boolean;
  disabled?: boolean;
  icon?: IconName;
  testID?: string;
  size?: "md" | "lg";
  style?: ViewStyle;
};

export function Button({ title, onPress, variant = "primary", loading, disabled, icon, testID, size = "md", style }: BtnProps) {
  const { colors } = useTheme();
  const s = useStyles();
  const bg = { primary: colors.brandPrimary, secondary: colors.brandSecondary, ghost: "transparent", danger: colors.error }[variant];
  const fg = { primary: colors.onBrandPrimary, secondary: colors.onBrandSecondary, ghost: colors.brandPrimary, danger: colors.onError }[variant];
  return (
    <Pressable
      testID={testID}
      disabled={disabled || loading}
      onPress={() => {
        if (Platform.OS !== "web") Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
        onPress();
      }}
      style={({ pressed }) => [
        s.btn,
        size === "lg" && s.btnLg,
        { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1, transform: [{ scale: pressed ? 0.98 : 1 }] },
        variant === "ghost" && { borderWidth: 1, borderColor: colors.border },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <>
          {icon && <Ionicons name={icon} size={size === "lg" ? 22 : 18} color={fg} />}
          <Text style={[s.btnText, size === "lg" && s.btnTextLg, { color: fg }]}>{title}</Text>
        </>
      )}
    </Pressable>
  );
}

// ---------- Field ----------
export function Field({ label, testID, ...props }: TextInputProps & { label: string }) {
  const { colors } = useTheme();
  const s = useStyles();
  const [focus, setFocus] = useState(false);
  return (
    <View style={s.field}>
      <Text style={s.label}>{label}</Text>
      <TextInput
        testID={testID}
        placeholderTextColor={colors.muted}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={[s.input, focus && { borderColor: colors.brandPrimary }, props.multiline && { height: 88, textAlignVertical: "top", paddingTop: 12 }]}
        {...props}
      />
    </View>
  );
}

// ---------- Chip ----------
export function Chip({ label, selected, onPress, testID, count }: { label: string; selected: boolean; onPress: () => void; testID?: string; count?: number }) {
  const { colors } = useTheme();
  const s = useStyles();
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={() => {
        tap();
        onPress();
      }}
      style={[s.chip, selected ? { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary } : null]}
    >
      <Text style={[s.chipText, { color: selected ? colors.onBrandPrimary : colors.onSurfaceTertiary }]}>{label}</Text>
      {count !== undefined && count > 0 && (
        <View style={[s.chipCount, { backgroundColor: selected ? colors.onBrandPrimary : colors.brandSecondary }]}>
          <Text style={[s.chipCountText, { color: selected ? colors.brandPrimary : colors.onBrandSecondary }]}>{count}</Text>
        </View>
      )}
    </Pressable>
  );
}

// ---------- Status badge ----------
export function StatusBadge({ status, testID }: { status: OrderStatus; testID?: string }) {
  const { colors } = useTheme();
  const s = useStyles();
  const c = statusColor(status, colors);
  return (
    <View testID={testID} style={[s.badge, { borderColor: c }]}>
      <View style={[s.dot, { backgroundColor: c }]} />
      <Text style={[s.badgeText, { color: colors.onSurface }]}>{STATUS_LABEL[status]}</Text>
    </View>
  );
}

// ---------- States ----------
export const EMPTY_IMG =
  "https://images.unsplash.com/photo-1651760680066-db9d32bd0357?crop=entropy&cs=srgb&fm=jpg&q=70&w=600";
export const COURIER_IMG =
  "https://images.unsplash.com/photo-1781603961241-bdca150ae684?crop=entropy&cs=srgb&fm=jpg&q=70&w=800";

export function EmptyState({ title, subtitle, image = EMPTY_IMG, action, testID }: { title: string; subtitle?: string; image?: string; action?: ReactNode; testID?: string }) {
  const s = useStyles();
  return (
    <View testID={testID} style={s.empty}>
      <Image source={{ uri: image }} style={s.emptyImg} contentFit="cover" transition={200} />
      <Text style={s.emptyTitle}>{title}</Text>
      {subtitle && <Text style={s.emptySub}>{subtitle}</Text>}
      {action}
    </View>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const s = useStyles();
  const { colors } = useTheme();
  return (
    <View testID="error-state" style={s.empty}>
      <Ionicons name="cloud-offline-outline" size={40} color={colors.error} />
      <Text style={s.emptyTitle}>{message}</Text>
      <Button testID="retry-button" title="Reintentar" variant="ghost" onPress={onRetry} />
    </View>
  );
}

export function Loading() {
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: space.xxl }}>
      <ActivityIndicator testID="loading-indicator" color={colors.brandPrimary} size="large" />
    </View>
  );
}

// ---------- Bottom sheet ----------
export function Sheet({ visible, onClose, title, children, testID }: { visible: boolean; onClose: () => void; title: string; children: ReactNode; testID?: string }) {
  const s = useStyles();
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose} statusBarTranslucent>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <Pressable testID={testID ? `${testID}-backdrop` : undefined} style={s.backdrop} onPress={onClose} />
        <View testID={testID} style={[s.sheet, { paddingBottom: insets.bottom + space.lg }]}>
          <View style={s.grabber} />
          <View style={s.sheetHead}>
            <Text style={s.sheetTitle}>{title}</Text>
            <Pressable testID={testID ? `${testID}-close` : undefined} onPress={onClose} hitSlop={12} style={s.iconBtn}>
              <Ionicons name="close" size={22} color={colors.onSurface} />
            </Pressable>
          </View>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ gap: space.md, paddingBottom: space.sm }}>
            {children}
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

// ---------- Toast ----------
type ToastT = { msg: string; kind: "ok" | "error" };
const ToastCtx = createContext<(msg: string, kind?: "ok" | "error") => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState<ToastT | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const s = useStyles();
  const show = useCallback((msg: string, kind: "ok" | "error" = "ok") => {
    if (timer.current) clearTimeout(timer.current);
    setT({ msg, kind });
    timer.current = setTimeout(() => setT(null), 2600);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {t && (
        <Animated.View entering={FadeInUp} exiting={FadeOutUp} pointerEvents="none" style={[s.toast, { bottom: insets.bottom + 96 }]}>
          <Ionicons name={t.kind === "ok" ? "checkmark-circle" : "alert-circle"} size={20} color={t.kind === "ok" ? colors.success : colors.error} />
          <Text testID="toast-message" style={s.toastText}>{t.msg}</Text>
        </Animated.View>
      )}
    </ToastCtx.Provider>
  );
}

const useStyles = makeStyles((c) => ({
  btn: {
    minHeight: 48,
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space.sm,
  },
  btnLg: { minHeight: 60, borderRadius: radius.lg },
  btnText: { fontFamily: font.bold, fontSize: 15 },
  btnTextLg: { fontSize: 18 },
  field: { gap: space.xs },
  label: { fontFamily: font.semibold, fontSize: 13, color: c.onSurfaceTertiary },
  input: {
    height: 48,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: c.border,
    backgroundColor: c.surfaceSecondary,
    paddingHorizontal: space.md,
    fontFamily: font.medium,
    fontSize: 15,
    color: c.onSurface,
  },
  chip: {
    height: 36,
    flexShrink: 0,
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: c.border,
    backgroundColor: c.surfaceSecondary,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  chipText: { fontFamily: font.semibold, fontSize: 13 },
  chipCount: { minWidth: 20, height: 20, borderRadius: 10, alignItems: "center", justifyContent: "center", paddingHorizontal: 5 },
  chipCountText: { fontFamily: font.bold, fontSize: 11 },
  badge: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, height: 26, borderRadius: radius.pill, borderWidth: 1, alignSelf: "flex-start" },
  dot: { width: 8, height: 8, borderRadius: 4 },
  badgeText: { fontFamily: font.semibold, fontSize: 12 },
  empty: { alignItems: "center", padding: space.xl, gap: space.md },
  emptyImg: { width: 160, height: 120, borderRadius: radius.lg },
  emptyTitle: { fontFamily: font.bold, fontSize: 16, color: c.onSurface, textAlign: "center" },
  emptySub: { fontFamily: font.regular, fontSize: 14, color: c.muted, textAlign: "center" },
  backdrop: { flex: 1, backgroundColor: c.overlay },
  sheet: {
    backgroundColor: c.surfaceSecondary,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    paddingHorizontal: space.lg,
    maxHeight: "88%",
  },
  grabber: { alignSelf: "center", width: 40, height: 5, borderRadius: 3, backgroundColor: c.borderStrong, marginTop: space.sm },
  sheetHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: space.md },
  sheetTitle: { fontFamily: font.bold, fontSize: 20, color: c.onSurface },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  toast: {
    position: "absolute",
    left: space.lg,
    right: space.lg,
    backgroundColor: c.surfaceInverse,
    borderRadius: radius.md,
    padding: space.md,
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
  },
  toastText: { fontFamily: font.semibold, fontSize: 14, color: c.onSurfaceInverse, flex: 1 },
}));
