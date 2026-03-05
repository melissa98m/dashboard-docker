"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiClientError, apiJson, getAuthEventName } from "../lib/api-client";

export interface AuthMeResponse {
  authenticated: boolean;
  username: string;
  role: string;
}

interface AuthErrorDetail {
  status?: number;
  message?: string;
}

interface AuthContextValue {
  loading: boolean;
  authenticated: boolean;
  me: AuthMeResponse | null;
  isAdmin: boolean;
  apiUnavailable: boolean;
  refreshAuthState: () => Promise<boolean>;
  openAuthPanel: () => void;
  registerOpenAuthPanel: (fn: () => void) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<AuthMeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiUnavailable, setApiUnavailable] = useState(false);
  const openAuthPanelRef = useRef<(() => void) | null>(null);

  const refreshAuthState = useCallback(async (): Promise<boolean> => {
    setApiUnavailable(false);
    try {
      const response = await apiJson<AuthMeResponse>("/api/auth/me");
      const isAuthenticated = response?.authenticated ?? false;
      setMe(isAuthenticated ? response : null);
      return isAuthenticated;
    } catch (error) {
      if (
        error instanceof ApiClientError &&
        (error.status === 401 || error.status === 403)
      ) {
        setMe(null);
        setApiUnavailable(false);
      } else {
        setMe(null);
        setApiUnavailable(true);
      }
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const openAuthPanel = useCallback(() => {
    openAuthPanelRef.current?.();
  }, []);

  const registerOpenAuthPanel = useCallback((fn: () => void) => {
    openAuthPanelRef.current = fn;
    return () => {
      openAuthPanelRef.current = null;
    };
  }, []);

  useEffect(() => {
    void refreshAuthState();

    const onAuthError = (event: Event) => {
      const customEvent = event as CustomEvent<AuthErrorDetail>;
      const status = customEvent.detail?.status;

      // Do not call refreshAuthState() here: it fetches /api/auth/me and would
      // re-emit auth errors, creating an event loop on persistent 401/403.
      if (status === 503) {
        setApiUnavailable(true);
      } else {
        setMe(null);
        setApiUnavailable(false);
      }
      setLoading(false);

      if (status === 401 || status === 403) {
        openAuthPanelRef.current?.();
      }
    };

    window.addEventListener(getAuthEventName(), onAuthError as EventListener);
    return () => {
      window.removeEventListener(
        getAuthEventName(),
        onAuthError as EventListener
      );
    };
  }, [refreshAuthState]);

  const value: AuthContextValue = {
    loading,
    authenticated: me?.authenticated ?? false,
    me,
    isAdmin: me?.role === "admin",
    apiUnavailable,
    refreshAuthState,
    openAuthPanel,
    registerOpenAuthPanel,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
