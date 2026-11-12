import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import API, { clearPhotoToken, setUnauthorizedHandler, TOKEN_KEY, User } from "@/src/api";
import { registerForPushNotifications } from "@/src/push";
import { storage } from "@/src/utils/storage";

type AuthCtx = {
  user: User | null;
  loading: boolean;
  signIn: (path: string, body: object) => Promise<User>;
  signOut: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const signedOut = useRef(false);
  const signOut = useCallback(async () => {
    signedOut.current = true;
    clearPhotoToken();
    await storage.secureDelete(TOKEN_KEY);
    setUser(null);
    API.clear();
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      signOut();
    });
  }, [signOut]);

  useEffect(() => {
    (async () => {
      const token = await storage.secureGet<string | null>(TOKEN_KEY, null);
      if (token) {
        try {
          const me = await API<User>("/auth/me");
          if (!signedOut.current) setUser(me);
        } catch {
          setUser(null);
        }
      }
      setLoading(false);
    })();
  }, [signOut]);

  const signIn = useCallback(async (path: string, body: object) => {
    const r = await API<any>(path, { method: "POST", body });

    if (!r || !r.token) {
      throw new Error("El servidor no devolvió un token válido");
    }

    signedOut.current = false;
    clearPhotoToken();
    await storage.secureSet(TOKEN_KEY, r.token);
    setUser(r.user);
    return r.user;
  }, []);

  useEffect(() => {
    if (user) registerForPushNotifications();
  }, [user]);

  return <Ctx.Provider value={{ user, loading, signIn, signOut }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const doCtx = useContext(Ctx);
  if (!doCtx) throw new Error("useAuth fuera de AuthProvider");
  return doCtx;
}
 
