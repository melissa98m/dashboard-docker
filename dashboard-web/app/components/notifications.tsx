"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type NotificationType = "info" | "success" | "error";

interface NotificationItem {
  id: number;
  message: string;
  type: NotificationType;
  leaving?: boolean;
}

interface NotificationsApi {
  info: (message: string) => void;
  success: (message: string) => void;
  error: (message: string) => void;
}

const NotificationsContext = createContext<NotificationsApi | null>(null);

function createId() {
  return Date.now() + Math.floor(Math.random() * 10000);
}

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<NotificationItem[]>([]);

  const dismiss = useCallback((id: number) => {
    setItems((previous) =>
      previous.map((item) => (item.id === id ? { ...item, leaving: true } : item))
    );
    window.setTimeout(() => {
      setItems((previous) => previous.filter((item) => item.id !== id));
    }, 170);
  }, []);

  const push = useCallback((message: string, type: NotificationType) => {
    const id = createId();
    setItems((previous) => [...previous, { id, message, type }].slice(-5));
    window.setTimeout(() => {
      dismiss(id);
    }, 3600);
  }, [dismiss]);

  const api = useMemo<NotificationsApi>(
    () => ({
      info: (message: string) => push(message, "info"),
      success: (message: string) => push(message, "success"),
      error: (message: string) => push(message, "error"),
    }),
    [push]
  );

  return (
    <NotificationsContext.Provider value={api}>
      {children}
      <div className="notifications-root" aria-live="polite" aria-atomic="true">
        {items.map((item) => (
          <div
            key={item.id}
            className={`notification notification-${item.type} ${
              item.leaving ? "notification-leaving" : ""
            }`}
          >
            <span>{item.message}</span>
            <button
              type="button"
              className="notification-close"
              onClick={() => dismiss(item.id)}
              aria-label="Fermer la notification"
            >
              x
            </button>
          </div>
        ))}
      </div>
    </NotificationsContext.Provider>
  );
}

export function useNotifications(): NotificationsApi {
  const value = useContext(NotificationsContext);
  if (!value) {
    throw new Error("useNotifications must be used within NotificationsProvider");
  }
  return value;
}
