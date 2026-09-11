import {
  createContext,
  startTransition,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { getMe, logout as apiLogout } from "../api/auth";

const SessionContext = createContext(null);

/**
 * Loads the account behind the session cookie once on boot (GET /me) and
 * shares it. `account` is null while signed out, and `loading` is true
 * until the first /me answer, so guards can wait instead of flashing the
 * login page.
 */
export function SessionProvider({ children }) {
  const [account, setAccount] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setAccount(await getMe());
    } catch {
      setAccount(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const signOut = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      // The cookie may already be dead; signed out either way.
    }
    // 025: a transition, like the router's own location updates, so a
    // caller's `signOut(); navigate(to)` commits in one render. As a
    // normal update the emptied session renders first, on the old path,
    // and RequireRole bounces it to /login before `to` is reached.
    startTransition(() => setAccount(null));
  }, []);

  const value = useMemo(
    () => ({ account, loading, refresh, setAccount, signOut }),
    [account, loading, refresh, signOut]
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession() {
  return useContext(SessionContext);
}
