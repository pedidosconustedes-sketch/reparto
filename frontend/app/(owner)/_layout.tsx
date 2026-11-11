import { Ionicons } from "@react-native-vector-icons/ionicons";
import { Redirect, Tabs } from "expo-router";
import { NativeTabs } from "expo-router/native-tabs";
import { Platform } from "react-native";

import { useQuery } from "@tanstack/react-query";

import { api, Order } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useIncidentAlert } from "@/src/incidentAlert";
import { font } from "@/src/fonts";
import { usesNativeTabs } from "@/src/navigation";
import { useTheme } from "@/src/theme";

type IconName = React.ComponentProps<typeof Ionicons>["name"];

const TABS: { name: string; label: string; sf: string; icon: IconName; iconOn: IconName }[] = [
  { name: "index", label: "Inicio", sf: "house.fill", icon: "home-outline", iconOn: "home" },
  { name: "orders", label: "Órdenes", sf: "list.bullet.rectangle.fill", icon: "receipt-outline", iconOn: "receipt" },
  { name: "map", label: "Mapa", sf: "map.fill", icon: "map-outline", iconOn: "map" },
  { name: "manage", label: "Gestión", sf: "square.grid.2x2.fill", icon: "grid-outline", iconOn: "grid" },
];

export default function OwnerLayout() {
  const { user, loading } = useAuth();
  const { colors } = useTheme();
  // Watch active orders on every owner tab so a new courier incident rings right away.
  const active = useQuery({
    queryKey: ["orders-active-watch"],
    queryFn: () => api<Order[]>("/orders?active=true"),
    refetchInterval: 10000,
    enabled: user?.role === "owner",
  });
  useIncidentAlert(active.data);
  if (loading) return null;
  if (user?.role !== "owner") return <Redirect href="/" />;

  if (usesNativeTabs) {
    return (
      <NativeTabs tintColor={colors.brandPrimary}>
        {TABS.map((t) => (
          <NativeTabs.Trigger key={t.name} name={t.name}>
            <NativeTabs.Trigger.Icon sf={t.sf as never} />
            <NativeTabs.Trigger.Label>{t.label}</NativeTabs.Trigger.Label>
          </NativeTabs.Trigger>
        ))}
      </NativeTabs>
    );
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary,
          borderTopColor: colors.border,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontFamily: font.semibold, fontSize: 11 },
      }}
    >
      {TABS.map((t) => (
        <Tabs.Screen
          key={t.name}
          name={t.name}
          options={{
            title: t.label,
            tabBarButtonTestID: `tab-${t.name}`,
            tabBarIcon: ({ color, focused }) => <Ionicons name={focused ? t.iconOn : t.icon} size={22} color={color} />,
          }}
        />
      ))}
    </Tabs>
  );
}
