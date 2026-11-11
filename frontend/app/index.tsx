import { Redirect } from "expo-router";

import { useAuth } from "@/src/auth";
import { Loading } from "@/src/components/ui";

export default function Index() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Redirect href="/login" />;
  return <Redirect href={user.role === "owner" ? "/(owner)" : user.role === "business" ? "/biz" : "/courier"} />;
}
