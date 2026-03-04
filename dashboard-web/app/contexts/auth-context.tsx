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

interface AuthContextValue {
  loading: boolean;
  authenticated: boolean;
  me: AuthMeResponse | null;
  isAdmin: boolean;
  apiUnavailable: boolean;
  refreshAuthState: () => Promise<void>;
  openAuthPanel: () => void;
  registerOpenAuthPanel: (fn: () => void) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<AuthMeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiUnavailable, setApiUnavailable] = useState(false);
  const openAuthPanelRef = useRef<(() => void) | null>(null);

  const refreshAuthState = useCallback(async (): Promise<void> => {
    setApiUnavailable(false);
    try {
      const response = await apiJson<AuthMeResponse>("/api/auth/me");
      setMe(response);
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 401) {
        setMe(null);
        setApiUnavailable(false);
      } else {
        setMe(null);
        setApiUnavailable(true);
      }
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

    const onAuthError = () => {
      setMe(null);
      openAuthPanelRef.current?.();
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
