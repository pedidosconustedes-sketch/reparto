import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Haptics from "expo-haptics";
import { Image } from "expo-image";
import * as Location from "expo-location";
import { Redirect, useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Linking, Platform, Pressable, RefreshControl, ScrollView, Switch, Text, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, money, Order, plural, num } from "@/src/api";
import { useAuth } from "@/src/auth";
import { ago } from "@/src/components/OrderCard";
import { CloseDeliverySheet } from "@/src/components/CloseDeliverySheet";
import { Elapsed } from "@/src/components/Elapsed";
import { NavSheet, NavTarget } from "@/src/components/NavSheet";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import { TRIP_ICON, TripMap, TripPoint, useTripColors } from "@/src/components/TripMap";
import { Button, COURIER_IMG, ErrorState, Ionicons, Loading, Sheet, StatusBadge, useToast } from "@/src/components/ui";
import { font, radius, space } from "@/src/fonts";
import { PAYMENT_ICON, PAYMENT_LABEL } from "@/src/status";
import { makeStyles, useTheme } from "@/src/theme";
import { ring } from "@/src/alert";
import { periodRange } from "@/src/period";
import { Avatar } from "@/src/components/Avatar";
import { BizPhoto } from "@/src/components/BizPhoto";
import { IncidentSheet } from "@/src/components/IncidentSheet";
import { NamedPhone, phoneLabel } from "@/src/components/PhonesEditor";
import { ProfilePhotoSheet } from "@/src/components/ProfilePhotoSheet";
import { startBackgroundLocation, stopBackgroundLocation } from "@/src/bgLocation";

type Perm = "unknown" | "granted" | "denied" | "blocked";

// Show the courier's own pin only when it's near the tasks, so the map stays zoomed on the work area.
function withNearbyMe(me: TripPoint, pts: TripPoint[]): TripPoint[] {
  const valid = pts.filter((p) => p.lat != null && p.lng != null);
  if (me.lat == null || me.lng == null || valid.length === 0) return me.lat == null ? pts : [me, ...pts];
  const lat = valid.reduce((a, p) => a + (p.lat as number), 0) / valid.length;
  const lng = valid.reduce((a, p) => a + (p.lng as number), 0) / valid.length;
  const near = Math.abs(me.lat - lat) < 1 && Math.abs(me.lng - lng) < 1.3;
  return near ? [me, ...pts] : pts;
}


export default function CourierHome() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const narrow = useWindowDimensions().width <= 340;
  const qc = useQueryClient();
  const router = useRouter();
  const toast = useToast();
  const { user, loading, signOut } = useAuth();
  const [online, setOnline] = useState(false);
  const [perm, setPerm] = useState<Perm>("unknown");
  const [permSheet, setPermSheet] = useState(false);
  const [closing, setClosing] = useState<Order | null>(null);
  const [pos, setPos] = useState<{ lat: number; lng: number } | null>(null);
  const tc = useTripColors();
  const watcher = useRef<Location.LocationSubscription | null>(null);

  const q = useQuery({
    queryKey: ["courier-orders"],
    queryFn: () =>
      api<{ active: Order[]; delivered: Order[]; cancelled: Order[]; emergency_phones: { name: string; phone: string }[]; pending_total: number; pending_count: number }>(
        `/courier/orders?since=${encodeURIComponent(periodRange("dia", new Date())[0].toISOString())}`,
      ),
    refetchInterval: 6000,
    enabled: user?.role === "courier",
  });

  // Ring + vibrate when a task is assigned to me or taken away / cancelled.
  const prevIds = useRef<Map<string, number> | null>(null);
  useEffect(() => {
    if (!q.data) return;
    const cur = new Map(q.data.active.map((o) => [o.id, o.number]));
    const delivered = new Set(q.data.delivered.map((o) => o.id));
    const prev = prevIds.current;
    prevIds.current = cur;
    if (!prev) return;
    const added = [...cur.entries()].filter(([id]) => !prev.has(id));
    const removed = [...prev.entries()].filter(([id]) => !cur.has(id) && !delivered.has(id));
    if (added.length || removed.length) {
      ring();
      if (added.length) toast(`Nueva tarea asignada: #${added.map(([, n]) => n).join(", #")}`);
      else toast(`Tarea cancelada o retirada: #${removed.map(([, n]) => n).join(", #")}`, "error");
    }
  }, [q.data, toast]);
  const [todayStart, todayEnd] = periodRange("dia", new Date());
  const todayQ = useQuery({
    queryKey: ["courier-history", todayStart.toISOString(), todayEnd.toISOString()],
    queryFn: () =>
      api<{ count: number; total_collected: number; total_fees: number }>(
        `/courier/history?start=${encodeURIComponent(todayStart.toISOString())}&end=${encodeURIComponent(todayEnd.toISOString())}`,
      ),
    enabled: user?.role === "courier",
  });

  const openQ = useQuery({
    queryKey: ["courier-open"],
    queryFn: () => api<Order[]>("/courier/open-orders"),
    refetchInterval: 6000,
    enabled: user?.role === "courier",
  });
  const prevOpen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!openQ.data) return;
    const cur = new Set(openQ.data.map((o) => o.id));
    const p = prevOpen.current;
    prevOpen.current = cur;
    if (!p) return;
    const fresh = openQ.data.filter((o) => !p.has(o.id));
    if (fresh.length) {
      ring();
      toast(`Nueva tarea libre: #${num(fresh[0].number)} · ${fresh[0].business_name}`);
    }
  }, [openQ.data, toast]);
  const accept = useMutation({
    mutationFn: (id: string) => api<Order>(`/courier/orders/${id}/accept`, { method: "POST" }),
    onSuccess: (o) => {
      if (Platform.OS !== "web") Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      // Treat as already known so the "assigned" ring doesn't fire for my own accept.
      prevIds.current?.set(o.id, o.number);
      qc.invalidateQueries({ queryKey: ["courier-open"] });
      qc.invalidateQueries({ queryKey: ["courier-orders"] });
      toast(`Tarea #${num(o.number)} aceptada`);
    },
    onError: (e: Error) => {
      qc.invalidateQueries({ queryKey: ["courier-open"] });
      toast(e.message, "error");
    },
  });
  const [photoOpen, setPhotoOpen] = useState(false);
  const [photo, setPhoto] = useState<string | null>(null);
  useEffect(() => {
    if (user?.role === "courier") setPhoto(user.profile_photo ?? null);
  }, [user]);
  const [bgSheet, setBgSheet] = useState(false);

  useEffect(() => {
    if (user?.role === "courier") setOnline(user.online);
  }, [user]);

  useEffect(() => {
    Location.getForegroundPermissionsAsync().then((p) => {
      setPerm(p.granted ? "granted" : p.status === "undetermined" ? "unknown" : p.canAskAgain ? "denied" : "blocked");
    });
    return () => watcher.current?.remove();
  }, []);

  const startWatch = useCallback(async () => {
    if (watcher.current) return;
    try {
      const send = (p: Location.LocationObject) => {
        setPos({ lat: p.coords.latitude, lng: p.coords.longitude });
        api("/courier/location", { method: "POST", body: { lat: p.coords.latitude, lng: p.coords.longitude } }).catch(() => {});
      };
      const first = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      send(first);
      watcher.current = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.Balanced, timeInterval: 15000, distanceInterval: 30 },
        send,
      );
      if (Platform.OS !== "web") {
        const bg = await Location.getBackgroundPermissionsAsync().catch(() => null);
        if (bg?.granted) startBackgroundLocation();
        else if (bg?.canAskAgain) setBgSheet(true);
      }
    } catch {
      toast("No pudimos obtener tu ubicación", "error");
    }
  }, [toast]);

  const stopWatch = () => {
    watcher.current?.remove();
    watcher.current = null;
    stopBackgroundLocation();
  };

  const allowBackground = async () => {
    setBgSheet(false);
    try {
      const p = await Location.requestBackgroundPermissionsAsync();
      if (p.granted) {
        const ok = await startBackgroundLocation();
        toast(ok ? "Ubicación activa también con la app cerrada" : "Disponible en la app publicada, no en la vista previa");
      } else if (!p.canAskAgain) {
        toast("Puedes activarlo en Ajustes > Ubicación > Siempre", "error");
      }
    } catch {
      toast("Disponible en la app publicada, no en la vista previa");
    }
  };

  // Resume sharing when reopening the app while online with permission.
  useEffect(() => {
    if (online && perm === "granted") startWatch();
    if (!online) stopWatch();
  }, [online, perm, startWatch]);

  const setOnlineApi = async (value: boolean) => {
    setOnline(value);
    await api("/courier/online", { method: "POST", body: { online: value } }).catch(() => toast("Sin conexión", "error"));
  };

  const toggleOnline = (value: boolean) => {
    if (value && perm !== "granted") {
      setPermSheet(true);
      return;
    }
    setOnlineApi(value);
  };

  const requestPerm = async () => {
    const p = await Location.requestForegroundPermissionsAsync();
    if (p.granted) {
      setPerm("granted");
      setPermSheet(false);
      setOnlineApi(true);
    } else {
      setPerm(p.canAskAgain ? "denied" : "blocked");
    }
  };

  const goOnlineWithoutLocation = () => {
    setPermSheet(false);
    setOnlineApi(true);
  };

  const update = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "en_camino" | "entregado" }) =>
      api<Order>(`/courier/orders/${id}/status`, { method: "PATCH", body: { status } }),
    onSuccess: (o) => {
      if (Platform.OS !== "web") Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      qc.invalidateQueries({ queryKey: ["courier-orders"] });
      qc.invalidateQueries({ queryKey: ["courier-history"] });
      toast(`Pedido #${num(o.number)} recogido`);
    },
    onError: (e: Error) => toast(e.message, "error"),
  });

  const [nav, setNav] = useState<NavTarget | null>(null);
  const [sos, setSos] = useState(false);
  const [incidentOrder, setIncidentOrder] = useState<Order | null>(null);
  const [callList, setCallList] = useState<{ title: string; phones: NamedPhone[] } | null>(null);
  if (loading) return <Loading />;
  if (user?.role !== "courier") return <Redirect href="/" />;

  const active = q.data?.active ?? [];
  const current = active[0];

  return (
    <View style={s.root}>
      <View style={[s.header, { paddingTop: insets.top + space.md }, narrow && { gap: space.sm, paddingHorizontal: space.md }]}>
        <Pressable testID="courier-profile-photo-button" accessibilityLabel="Foto de perfil" onPress={() => setPhotoOpen(true)}>
          <Avatar userId={user?.id ?? ""} name={user?.name ?? ""} hasPhoto={!!photo} version={photo} size={44} />
          <View style={s.camBadge}><Ionicons name="camera" size={11} color={colors.onBrandPrimary} /></View>
        </Pressable>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={[s.hello, narrow && { fontSize: 18 }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>{user?.name?.split(" ")[0]}</Text>
          <View style={s.statusRow}>
            <View style={[s.dot, { backgroundColor: online ? colors.success : colors.muted }]} />
            <Text testID="courier-online-label" style={[s.statusText, { flexShrink: 1 }]} numberOfLines={1}>
              {online ? "En línea" : "Desconectado"}{online && perm === "granted" && !narrow ? " · GPS" : ""}
            </Text>
          </View>
        </View>
        <Switch
          testID="courier-online-switch"
          value={online}
          onValueChange={toggleOnline}
          trackColor={{ true: colors.success, false: colors.borderStrong }}
          thumbColor={colors.surfaceSecondary}
        />
        <Pressable testID="emergency-button" accessibilityLabel="Emergencia" onPress={() => setSos(true)} style={[s.sosBtn, narrow && { paddingHorizontal: 0, width: 44, justifyContent: "center" }]}>
          <Ionicons name="alert-circle" size={20} color={colors.onError} />
          {!narrow && <Text style={s.sosText}>SOS</Text>}
        </Pressable>
        <Pressable testID="courier-logout-button" onPress={() => { stopWatch(); setOnlineApi(false); signOut(); }} style={s.iconBtn}>
          <Ionicons name="log-out-outline" size={24} color={colors.error} />
        </Pressable>
      </View>

      {q.isLoading ? (
        <Loading />
      ) : q.isError ? (
        <ErrorState message="Error de conexión" onRetry={() => q.refetch()} />
      ) : (
        <ScrollView
          contentContainerStyle={[s.content, { paddingBottom: insets.bottom + space.xl }]}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => { q.refetch(); }} tintColor={colors.brandPrimary} />}
        >
          <Pressable testID="open-history-button" onPress={() => router.push("/courier-history")} style={({ pressed }) => [s.todayCard, { opacity: pressed ? 0.9 : 1 }]}>
            <View style={{ flex: 1 }}>
              <Text style={s.todayLabel}>Envíos de hoy</Text>
              <Text testID="today-total" style={s.todayValue}>{money(todayQ.data?.total_collected ?? 0)}</Text>
              <Text style={s.todayMeta}>{plural(todayQ.data?.count ?? 0, "tarea entregada", "tareas entregadas")}</Text>
              <Text testID="pending-payout" style={s.todayMeta}>Pendiente de cobro: {money(q.data?.pending_total ?? 0)}</Text>
            </View>
            <View style={s.todayLink}>
              <Ionicons name="calendar-outline" size={18} color={colors.onBrandPrimary} />
              <Text style={s.todayLinkText}>Historial</Text>
            </View>
          </Pressable>
          {(active.length > 0 || (openQ.data ?? []).length > 0) && (
            <View testID="courier-home-map" style={s.homeMap}>
              <TripMap
                big
                style={{ flex: 1 }}
                points={withNearbyMe(
                  { id: "me", kind: "courier", lat: pos?.lat ?? user?.lat, lng: pos?.lng ?? user?.lng, title: "Tu ubicación" },
                  [
                  ...active.flatMap((o): TripPoint[] => [
                    ...(o.status !== "en_camino" ? [{ id: `p-${o.id}`, kind: "pickup" as const, lat: o.pickup_lat, lng: o.pickup_lng, title: `#${num(o.number)} Recoger: ${o.business_name}` }] : []),
                    { id: `d-${o.id}`, kind: "dest", lat: o.dest_lat, lng: o.dest_lng, title: `#${num(o.number)} Entregar: ${o.address}` },
                  ]),
                  ...(openQ.data ?? []).flatMap((o): TripPoint[] => [
                    { id: `op-${o.id}`, kind: "pickup", lat: o.pickup_lat, lng: o.pickup_lng, title: `LIBRE #${num(o.number)} Recoger: ${o.business_name}` },
                    { id: `od-${o.id}`, kind: "dest", lat: o.dest_lat, lng: o.dest_lng, title: `LIBRE #${num(o.number)} Entregar: ${o.address}` },
                  ]),
                ])}
              />
            </View>
          )}
          {(openQ.data ?? []).length > 0 && (
            <>
              <Text style={s.section}>Tareas libres ({openQ.data?.length})</Text>
              {openQ.data?.map((o) => (
                <View key={o.id} testID={`open-order-${o.number}`} style={s.openCard}>
                  <View style={s.rowBetween}>
                    <Text style={s.kicker}>LIBRE · #{num(o.number)}</Text>
                    <Text style={s.openFee}>{money(o.delivery_fee)}</Text>
                  </View>
                  <View style={s.metaRow}>
                    <BizPhoto businessId={o.business_id} photo={o.business_photo} size={28} />
                    <Text style={s.stopAddr} numberOfLines={2}>{o.business_name}{o.pickup_address ? ` · ${o.pickup_address}` : ""}</Text>
                  </View>
                  <View style={s.metaRow}>
                    <Ionicons name="location" size={18} color={tc.dest} />
                    <Text style={s.meta} numberOfLines={2}>{o.address}</Text>
                  </View>
                  {!!o.scheduled_for && (
                    <Text style={s.meta}>Programado: {format(new Date(o.scheduled_for), "EEEE d MMM, HH:mm", { locale: es })}</Text>
                  )}
                  <Button testID={`accept-${o.number}`} title="Aceptar tarea" icon="hand-left" size="lg" loading={accept.isPending && accept.variables === o.id} onPress={() => accept.mutate(o.id)} />
                </View>
              ))}
            </>
          )}
          {active.length + (openQ.data?.length ?? 0) > 1 && (
            <Button testID="open-all-tasks-map" title="Ver el mapa a pantalla completa" icon="expand" variant="ghost" onPress={() => router.push("/courier-map")} />
          )}
          {!current ? (
            <View testID="courier-empty" style={s.emptyCard}>
              <Image source={{ uri: COURIER_IMG }} style={s.hero} contentFit="cover" transition={200} />
              <Text style={s.emptyTitle}>No tienes entregas asignadas.</Text>
              <Text style={s.emptySub}>{online ? "Estás en línea. Te avisaremos aquí cuando tengas una." : "Conéctate para empezar a recibir entregas."}</Text>
            </View>
          ) : (
            active.map((o, i) => (
              <View key={o.id} testID={`courier-order-${o.number}`} style={[s.big, i > 0 && s.queued]}>
                <View style={s.rowBetween}>
                  <Text style={s.kicker}>{i === 0 ? "ENTREGA ACTUAL" : "SIGUIENTE"} · #{num(o.number)}</Text>
                  <StatusBadge status={o.status} />
                </View>
                <View style={s.metaRow}>
                  <Ionicons name="time-outline" size={18} color={colors.warning} />
                  <Elapsed testID={`elapsed-${o.number}`} from={o.assigned_at ?? o.created_at} prefix="Llevas " style={s.elapsed} />
                </View>
                {!!o.scheduled_for && (
                  <View style={s.metaRow}>
                    <Ionicons name="calendar" size={18} color={colors.info} />
                    <Text style={s.meta}>Programado: {format(new Date(o.scheduled_for), "EEEE d MMM, HH:mm", { locale: es })}</Text>
                  </View>
                )}
                <View style={s.metaRow}>
                  <BizPhoto businessId={o.business_id} photo={o.business_photo} size={36} />
                  <Text style={s.customer}>{o.customer_name}</Text>
                </View>
                {(["pickup", "dest"] as const).map((k) => {
                  const done = k === "pickup" && o.status === "en_camino";
                  const addr = k === "pickup" ? o.pickup_address || o.business_name : o.address;
                  return (
                    <View key={k} testID={`stop-${k}-${o.number}`} style={[s.stop, done && { opacity: 0.5 }]}>
                      <View style={[s.stopIcon, { backgroundColor: tc[k] }]}>
                        <Ionicons name={done ? "checkmark" : TRIP_ICON[k]} size={18} color="#FFFFFF" />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={s.stopLabel}>{k === "pickup" ? `RECOGER EN ${o.business_name.toUpperCase()}` : "ENTREGAR EN"}</Text>
                        <Text style={s.stopAddr}>{addr}</Text>
                      </View>
                      {k === "pickup" && (!!o.pickup_phone || (o.pickup_phones?.length ?? 0) > 0) && (
                        <Pressable
                          testID={`call-business-${o.number}`}
                          onPress={() => {
                            const list = o.pickup_phones?.length ? o.pickup_phones : [{ name: "", phone: o.pickup_phone as string }];
                            if (list.length === 1) Linking.openURL(`tel:${list[0].phone}`);
                            else setCallList({ title: `Llamar a ${o.business_name}`, phones: list });
                          }}
                          style={s.navBtn}
                        >
                          <Ionicons name="call" size={20} color={colors.brandPrimary} />
                        </Pressable>
                      )}
                      <Pressable
                        testID={`nav-${k}-${o.number}`}
                        onPress={() => setNav({ address: addr, lat: k === "pickup" ? o.pickup_lat : o.dest_lat, lng: k === "pickup" ? o.pickup_lng : o.dest_lng })}
                        style={s.navBtn}
                      >
                        <Ionicons name="navigate" size={20} color={colors.brandPrimary} />
                      </Pressable>
                    </View>
                  );
                })}
                {!!o.notes && (
                  <View style={s.metaRow}>
                    <Ionicons name="document-text-outline" size={18} color={colors.muted} />
                    <Text style={s.meta}>{o.notes}</Text>
                  </View>
                )}
                <View style={s.metaRow}>
                  <Ionicons name={PAYMENT_ICON[o.payment_method ?? "efectivo"]} size={18} color={colors.muted} />
                  <Text testID={`courier-payment-${o.number}`} style={s.meta}>
                    {(o.payment_method ?? "efectivo") === "pagado"
                      ? `Ya pagado (${money(o.total)}): no cobrar`
                      : `Cobrar ${money(o.total)} · ${PAYMENT_LABEL[o.payment_method ?? "efectivo"]}`}
                  </Text>
                </View>
                {!!o.customer_phone && (
                  <Button testID={`call-${o.number}`} title="Llamar al cliente" icon="call" variant="ghost" onPress={() => Linking.openURL(`tel:${o.customer_phone}`)} />
                )}
                <Button testID={`incident-${o.number}`} title={`Reportar incidencia${o.incidents?.length ? ` (${o.incidents.length})` : ""}`} icon="warning-outline" variant="ghost" onPress={() => setIncidentOrder(o)} />
                <View testID={`proof-hint-${o.number}`} style={s.proofHint}>
                  <Ionicons name="camera" size={18} color={colors.onBrandSecondary} />
                  <Text style={s.proofHintText}>
                    {o.status === "en_camino"
                      ? "Al pulsar Entregar tomas la foto del pedido y dejas una nota."
                      : "Después de recoger, podrás tomar una foto y dejar una nota antes de entregar."}
                  </Text>
                </View>
                {o.status === "en_camino" ? (
                  <Button testID={`deliver-${o.number}`} title="Foto, nota y entregar" icon="camera" size="lg" onPress={() => setClosing(o)} />
                ) : (
                  <Button testID={`start-${o.number}`} title="Recoger" icon="bag-handle" size="lg" loading={update.isPending && update.variables?.id === o.id} onPress={() => update.mutate({ id: o.id, status: "en_camino" })} />
                )}
              </View>
            ))
          )}

          {!!q.data?.delivered.length && (
            <>
              <Text style={s.section}>Entregadas hoy</Text>
              {q.data.delivered.map((o) => {
                const at = [...(o.history ?? [])].reverse().find((h) => h.status === "entregado")?.at ?? o.updated_at;
                return (
                  <View key={o.id} testID={`delivered-${o.number}`} style={s.doneRow}>
                    <BizPhoto businessId={o.business_id} photo={o.business_photo} size={40} />
                    <View style={{ flex: 1 }}>
                      <Text style={s.doneTitle} numberOfLines={1}>#{num(o.number)} · {o.business_name}</Text>
                      <Text style={s.meta} numberOfLines={2}>{o.address}</Text>
                      <Text style={s.meta}>Entregado a las {format(new Date(at), "HH:mm")} · {o.customer_name}</Text>
                    </View>
                    <Text style={s.doneTitle}>{money(o.delivery_fee)}</Text>
                  </View>
                );
              })}
            </>
          )}
          {!!q.data?.cancelled.length && (
            <>
              <Text style={s.section}>Canceladas hoy</Text>
              {q.data.cancelled.map((o) => (
                <View key={o.id} testID={`cancelled-${o.number}`} style={s.doneRow}>
                  <Ionicons name="close-circle" size={22} color={colors.error} />
                  <View style={{ flex: 1 }}>
                    <Text style={s.doneTitle} numberOfLines={1}>#{num(o.number)} · {o.customer_name}</Text>
                    <Text style={s.meta}>{ago(o.updated_at)}</Text>
                  </View>
                </View>
              ))}
            </>
          )}
        </ScrollView>
      )}

      <Sheet testID="location-permission-sheet" visible={permSheet} onClose={() => setPermSheet(false)} title="Comparte tu ubicación">
        <View style={s.permIcon}><Ionicons name="location" size={28} color={colors.onBrandSecondary} /></View>
        <Text style={s.permText}>
          Así el comercio ve dónde estás en el mapa y puede asignarte entregas cercanas. Solo se comparte mientras estás en línea y la app está abierta.
        </Text>
        {perm === "blocked" ? (
          <>
            <Text style={s.permWarn}>El permiso de ubicación está desactivado. Actívalo desde los ajustes del teléfono.</Text>
            <Button testID="open-settings-button" title="Abrir ajustes" icon="settings-outline" onPress={() => Linking.openSettings()} />
          </>
        ) : (
          <Button testID="allow-location-button" title={perm === "denied" ? "Intentar de nuevo" : "Permitir ubicación"} icon="location-outline" onPress={requestPerm} />
        )}
        <Button testID="online-without-location-button" title="Conectarme sin ubicación" variant="ghost" onPress={goOnlineWithoutLocation} />
      </Sheet>
      <NavSheet target={nav} onClose={() => setNav(null)} />
      <IncidentSheet order={incidentOrder} onClose={() => setIncidentOrder(null)} onSaved={() => qc.invalidateQueries({ queryKey: ["courier-orders"] })} />
      <Sheet testID="call-list-sheet" visible={!!callList} onClose={() => setCallList(null)} title={callList?.title ?? ""}>
        {callList?.phones.map((p, i) => (
          <Button key={i} testID={`call-list-${i}`} title={phoneLabel(p)} icon="call" variant={i === 0 ? "primary" : "ghost"} onPress={() => Linking.openURL(`tel:${p.phone}`)} />
        ))}
      </Sheet>
      <ProfilePhotoSheet visible={photoOpen} onClose={() => setPhotoOpen(false)} userId={user?.id ?? ""} name={user?.name ?? ""} photo={photo} onSaved={setPhoto} />
      <Sheet testID="bg-location-sheet" visible={bgSheet} onClose={() => setBgSheet(false)} title="¿Seguir compartiendo con la app cerrada?">
        <Text style={s.permText}>
          Si lo permites, el administrador seguirá viendo dónde estás aunque cierres la app o bloquees el móvil, mientras estés en línea. Elige «Permitir siempre» en el siguiente aviso.
        </Text>
        <Button testID="allow-bg-location" title="Permitir con la app cerrada" icon="location" onPress={allowBackground} />
        <Button testID="skip-bg-location" title="Solo con la app abierta" variant="ghost" onPress={() => setBgSheet(false)} />
      </Sheet>
      <Sheet testID="emergency-sheet" visible={sos} onClose={() => setSos(false)} title="Llamar a un administrador">
        {(q.data?.emergency_phones ?? []).length === 0 && <Text style={s.meta}>El administrador aún no ha añadido teléfonos de emergencia.</Text>}
        {(q.data?.emergency_phones ?? []).map((p, i) => (
          <Button key={`${p.phone}-${i}`} testID={`emergency-call-${i}`} title={`Llamar a ${p.name || "administrador"} · ${p.phone}`} icon="call" variant={i === 0 ? "danger" : "ghost"} onPress={() => Linking.openURL(`tel:${p.phone}`)} />
        ))}
      </Sheet>
      <CloseDeliverySheet
        order={closing}
        onClose={() => setClosing(null)}
        onDone={(o) => {
          setClosing(null);
          if (Platform.OS !== "web") Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          qc.invalidateQueries({ queryKey: ["courier-orders"] });
          qc.invalidateQueries({ queryKey: ["courier-history"] });
          toast(`¡Orden #${num(o.number)} entregada!`);
        }}
      />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingHorizontal: space.lg, paddingBottom: space.md, borderBottomWidth: 1, borderBottomColor: c.divider },
  hello: { fontFamily: font.extrabold, fontSize: 22, color: c.onSurface, letterSpacing: -0.5, flexShrink: 1 },
  statusRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  statusText: { fontFamily: font.semibold, fontSize: 14, color: c.muted },
  dot: { width: 10, height: 10, borderRadius: 5 },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  content: { padding: space.lg, gap: space.lg },
  big: { backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: c.border, padding: space.xl, gap: space.md },
  queued: { opacity: 0.92 },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  kicker: { fontFamily: font.bold, fontSize: 12, color: c.brandPrimary, letterSpacing: 1 },
  address: { fontFamily: font.extrabold, fontSize: 24, color: c.onSurface, lineHeight: 30 },
  customer: { fontFamily: font.semibold, fontSize: 18, color: c.onSurfaceTertiary },
  metaRow: { flexDirection: "row", alignItems: "center", gap: space.sm },
  meta: { fontFamily: font.medium, fontSize: 15, color: c.muted, flex: 1 },
  actions: { flexDirection: "row", gap: space.sm, marginTop: space.xs },
  emptyCard: { alignItems: "center", gap: space.md, paddingVertical: space.xl },
  hero: { width: "100%", height: 200, borderRadius: radius.lg },
  emptyTitle: { fontFamily: font.bold, fontSize: 20, color: c.onSurface, textAlign: "center" },
  emptySub: { fontFamily: font.regular, fontSize: 15, color: c.muted, textAlign: "center" },
  section: { fontFamily: font.bold, fontSize: 18, color: c.onSurface, marginTop: space.sm },
  doneRow: { flexDirection: "row", alignItems: "center", gap: space.md, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, padding: space.md },
  doneTitle: { fontFamily: font.bold, fontSize: 15, color: c.onSurface },
  permIcon: { width: 56, height: 56, borderRadius: 28, backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center" },
  permText: { fontFamily: font.medium, fontSize: 15, color: c.onSurfaceTertiary, lineHeight: 22 },
  permWarn: { fontFamily: font.semibold, fontSize: 14, color: c.error },
  map: { height: 220, borderRadius: radius.md, overflow: "hidden" },
  proofHint: { flexDirection: "row", alignItems: "center", gap: space.sm, backgroundColor: c.brandSecondary, borderRadius: radius.md, padding: space.md },
  elapsed: { fontFamily: font.bold, fontSize: 15, color: c.warning },
  sosBtn: { flexDirection: "row", alignItems: "center", gap: 4, height: 40, paddingHorizontal: space.md, borderRadius: radius.pill, backgroundColor: c.error },
  sosText: { fontFamily: font.extrabold, fontSize: 13, color: c.onError },
  proofHintText: { fontFamily: font.semibold, fontSize: 13, color: c.onBrandSecondary, flex: 1 },
  stop: { flexDirection: "row", alignItems: "center", gap: space.md, backgroundColor: c.surface, borderRadius: radius.md, padding: space.md },
  stopIcon: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  stopLabel: { fontFamily: font.bold, fontSize: 11, color: c.muted, letterSpacing: 0.5 },
  stopAddr: { fontFamily: font.bold, fontSize: 16, color: c.onSurface },
  navBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  todayCard: { flexDirection: "row", alignItems: "center", backgroundColor: c.brandPrimary, borderRadius: radius.lg, padding: space.lg, gap: space.md },
  todayLabel: { fontFamily: font.semibold, fontSize: 13, color: c.onBrandPrimary, opacity: 0.85 },
  todayValue: { fontFamily: font.extrabold, fontSize: 28, color: c.onBrandPrimary },
  todayMeta: { fontFamily: font.medium, fontSize: 13, color: c.onBrandPrimary, opacity: 0.85 },
  todayLink: { alignItems: "center", gap: 2, minWidth: 64, minHeight: 44, justifyContent: "center" },
  todayLinkText: { fontFamily: font.bold, fontSize: 12, color: c.onBrandPrimary },
  camBadge: { position: "absolute", right: -2, bottom: -2, width: 20, height: 20, borderRadius: 10, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: c.surface },
  openCard: { backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 2, borderColor: c.brandPrimary, padding: space.lg, gap: space.sm },
  openFee: { fontFamily: font.extrabold, fontSize: 18, color: c.onSurface },
  homeMap: { height: 380, borderRadius: radius.lg, overflow: "hidden", borderWidth: 1, borderColor: c.border },
}));
