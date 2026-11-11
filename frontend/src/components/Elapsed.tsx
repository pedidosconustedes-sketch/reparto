import { differenceInMinutes } from "date-fns";
import { useEffect, useState } from "react";
import { Text, TextStyle, StyleProp } from "react-native";

export function useNow(intervalMs = 30000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export function formatElapsed(fromIso: string, now: number) {
  const m = Math.max(0, differenceInMinutes(now, new Date(fromIso)));
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h >= 24) return `${Math.floor(h / 24)} d ${h % 24} h`;
  return `${h} h ${m % 60} min`;
}

export function Elapsed({ from, style, testID, prefix = "" }: { from: string; style?: StyleProp<TextStyle>; testID?: string; prefix?: string }) {
  const now = useNow();
  return <Text testID={testID} style={style}>{prefix}{formatElapsed(from, now)}</Text>;
}
