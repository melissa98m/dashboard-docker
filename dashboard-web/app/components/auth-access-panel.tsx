"use client";

import { FormEvent, useEffect, useState } from "react";

import { ApiClientError, apiFetch, getAuthEventName } from "../lib/api-client";
import { useAuth } from "../contexts/auth-context";

interface AuthErrorDetail {
  status: number;
  message: string;
}

export default function AuthAccessPanel() {
  const { me, loading, refreshAuthState, registerOpenAuthPanel } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [authError, setAuthError] = useState<AuthErrorDetail | null>(null);

  useEffect(() => {
    return registerOpenAuthPanel(() => setIsOpen(true));
  }, [registerOpenAuthPanel]);

  useEffect(() => {
    const onAuthError = (event: Event) => {
      const custom = event as CustomEvent<AuthErrorDetail>;
      const detail = custom.detail;
      if (!detail || typeof detail.message !== "string") return;
      setAuthError({
        status: detail.status,
        message: detail.message,
      });
      setIsOpen(true);
    };

    window.addEventListener(getAuthEventName(), onAuthError as EventListener);
    return () => {
      window.removeEventListener(getAuthEventName(), onAuthError as EventListener);
    };
  }, []);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setAuthError(null);
    try {
      await apiFetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      setPassword("");
      window.location.reload();
    } catch (error) {
      if (error instanceof ApiClientError) {
        setAuthError({ status: error.status, message: error.message });
      } else if (error instanceof Error) {
        setAuthError({ status: 0, message: error.message });
      } else {
        setAuthError({ status: 0, message: "Connexion impossible" });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onLogout = async () => {
    setSubmitting(true);
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
      await refreshAuthState();
    } finally {
      setSubmitting(false);
      setIsOpen(false);
    }
  };

  const buttonLabel = loading ? "Auth" : me ? `Connecte: ${me.username}` : "Se connecter";

  return (
    <div className="auth-panel">
      <button
        type="button"
        className="theme-toggle"
        onClick={() => setIsOpen((previous) => !previous)}
        aria-expanded={isOpen}
      >
        <span aria-hidden="true">AUTH</span>
        <span>{buttonLabel}</span>
      </button>
      {isOpen && (
        <form onSubmit={onSubmit} className="auth-panel-popover panel">
          <p className="text-sm font-semibold mb-2">Session utilisateur</p>
          {authError && (
            <p className="text-xs text-red-400 mb-2">
              Erreur {authError.status}: {authError.message}
            </p>
          )}
          {me ? (
            <div className="mb-2 text-xs text-slate-300">
              <p>Utilisateur: {me.username}</p>
              <p>Role: {me.role}</p>
            </div>
          ) : null}
          <label>
            <span className="field-label">Nom d&apos;utilisateur</span>
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="admin"
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700 mb-2"
              autoComplete="username"
            />
          </label>
          <label>
            <span className="field-label">Mot de passe</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Saisir le mot de passe"
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700 mb-2"
              autoComplete="current-password"
            />
          </label>
          <div className="btn-row">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || !username.trim() || !password}
            >
              {submitting ? "Connexion..." : "Connexion"}
            </button>
            <button type="button" className="btn btn-neutral" onClick={onLogout} disabled={submitting || !me}>
              Deconnexion
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
