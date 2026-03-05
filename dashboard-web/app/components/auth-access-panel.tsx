"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import {
  ApiClientError,
  apiFetch,
  apiJson,
  getAuthEventName,
} from "../lib/api-client";
import { useAuth } from "../contexts/auth-context";

interface AuthErrorDetail {
  status: number;
  message: string;
}

interface LoginResponse {
  authenticated: boolean;
  username: string;
  role: string;
  mfa_required?: boolean;
  mfa_token?: string | null;
}

interface TotpStatusResponse {
  enabled: boolean;
}

interface TotpSetupResponse {
  enrollment_token: string;
  manual_entry_key: string;
  otpauth_uri: string;
}

export default function AuthAccessPanel() {
  const { me, loading, refreshAuthState, registerOpenAuthPanel } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [totpEnabled, setTotpEnabled] = useState<boolean | null>(null);
  const [totpSetup, setTotpSetup] = useState<TotpSetupResponse | null>(null);
  const [totpEnableCode, setTotpEnableCode] = useState("");
  const [totpQrDataUrl, setTotpQrDataUrl] = useState<string | null>(null);
  const [totpEnrollmentRequired, setTotpEnrollmentRequired] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [authError, setAuthError] = useState<AuthErrorDetail | null>(null);

  const mfaJson = async <T,>(
    path: string,
    init?: RequestInit
  ): Promise<T> => {
    const response = await fetch(path, {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
    });
    if (!response.ok) {
      let message = "Erreur MFA";
      try {
        const payload = (await response.json()) as { detail?: string };
        if (typeof payload.detail === "string" && payload.detail.trim()) {
          message = payload.detail;
        }
      } catch {
        // ignore parse errors
      }
      throw new ApiClientError(message, response.status);
    }
    return (await response.json()) as T;
  };

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
      window.removeEventListener(
        getAuthEventName(),
        onAuthError as EventListener
      );
    };
  }, []);

  useEffect(() => {
    if (!me) {
      setTotpEnabled(null);
      setTotpSetup(null);
      setTotpEnrollmentRequired(false);
      return;
    }
    void (async () => {
      try {
        const payload = await mfaJson<TotpStatusResponse>("/api/auth/2fa/status");
        setTotpEnabled(payload.enabled);
        if (payload.enabled) {
          setTotpEnrollmentRequired(false);
        }
      } catch {
        setTotpEnabled(null);
      }
    })();
  }, [me?.username]);

  useEffect(() => {
    if (!totpSetup?.otpauth_uri) {
      setTotpQrDataUrl(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const qrCode = await import("qrcode");
        const toDataURL =
          qrCode.toDataURL ?? qrCode.default?.toDataURL ?? null;
        if (!toDataURL) throw new Error("QR encoder unavailable");
        const nextUrl = await toDataURL(totpSetup.otpauth_uri, {
          errorCorrectionLevel: "M",
          margin: 1,
          width: 220,
        });
        if (!cancelled) setTotpQrDataUrl(nextUrl);
      } catch {
        if (!cancelled) setTotpQrDataUrl(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [totpSetup?.otpauth_uri]);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setAuthError(null);
    try {
      const payload = await apiJson<LoginResponse>("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (payload.mfa_required && payload.mfa_token) {
        setMfaToken(payload.mfa_token);
        setPassword("");
        return;
      }
      setPassword("");
      setMfaToken(null);
      setOtpCode("");
      setAuthError(null);
      await refreshAuthState();
      const statusPayload = await mfaJson<TotpStatusResponse>("/api/auth/2fa/status");
      setTotpEnabled(statusPayload.enabled);
      if (!statusPayload.enabled) {
        setTotpEnrollmentRequired(true);
        setIsOpen(true);
        await onStartTotpSetup();
      } else {
        setTotpEnrollmentRequired(false);
        setIsOpen(false);
      }
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

  const onVerifyMfa = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!mfaToken) return;
    setSubmitting(true);
    setAuthError(null);
    try {
      await apiFetch("/api/auth/login/verify-2fa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mfa_token: mfaToken, otp_code: otpCode }),
      });
      setOtpCode("");
      setMfaToken(null);
      await refreshAuthState();
      setIsOpen(false);
    } catch (error) {
      if (error instanceof ApiClientError) {
        setAuthError({ status: error.status, message: error.message });
      } else if (error instanceof Error) {
        setAuthError({ status: 0, message: error.message });
      } else {
        setAuthError({ status: 0, message: "Vérification MFA impossible" });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onStartTotpSetup = async () => {
    setSubmitting(true);
    setAuthError(null);
    try {
      const setup = await mfaJson<TotpSetupResponse>("/api/auth/2fa/setup", {
        method: "POST",
      });
      setTotpSetup(setup);
      setTotpQrDataUrl(null);
      setTotpEnableCode("");
    } catch (error) {
      if (error instanceof ApiClientError) {
        setAuthError({ status: error.status, message: error.message });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onEnableTotp = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!totpSetup) return;
    setSubmitting(true);
    setAuthError(null);
    try {
      await mfaJson<{ enabled: boolean }>("/api/auth/2fa/enable", {
        method: "POST",
        body: JSON.stringify({
          enrollment_token: totpSetup.enrollment_token,
          otp_code: totpEnableCode,
        }),
      });
      setTotpEnabled(true);
      setTotpSetup(null);
      setTotpEnableCode("");
      setTotpEnrollmentRequired(false);
    } catch (error) {
      if (error instanceof ApiClientError) {
        setAuthError({ status: error.status, message: error.message });
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
      setTotpEnrollmentRequired(false);
      setIsOpen(false);
    }
  };

  const buttonLabel = loading
    ? "Auth"
    : me
      ? `Connecté : ${me.username}`
      : "Se connecter";

  const authModal = isOpen ? (
    <>
      <button
        type="button"
        className="auth-panel-backdrop"
        onClick={() => {
          if (!totpEnrollmentRequired) setIsOpen(false);
        }}
        aria-label="Fermer le formulaire de connexion"
      />
      <div className="auth-panel-popover panel">
        <p className="text-sm font-semibold mb-2">Session utilisateur</p>
        {totpEnrollmentRequired && (
          <p className="text-xs text-amber-300 mb-2">
            Configuration OTP requise: scanne le QR code puis valide le code à
            6 chiffres.
          </p>
        )}
        {authError && (
          <p className="text-xs text-red-400 mb-2">
            Erreur {authError.status} : {authError.message}
          </p>
        )}
        {me ? (
          <>
            <div className="mb-3 text-xs text-slate-300">
              <p>Utilisateur : {me.username}</p>
              <p>Rôle : {me.role}</p>
              <p>
                MFA :{" "}
                {totpEnabled === null
                  ? "inconnu"
                  : totpEnabled
                    ? "activée"
                    : "désactivée"}
              </p>
            </div>
            {!totpEnabled && !totpSetup && (
              <button
                type="button"
                className="btn btn-primary w-full mb-2"
                onClick={onStartTotpSetup}
                disabled={submitting}
              >
                Configurer 2FA
              </button>
            )}
            {totpSetup && (
              <form onSubmit={onEnableTotp} className="space-y-2 mb-2">
                {totpQrDataUrl ? (
                  <img
                    src={totpQrDataUrl}
                    alt="QR code OTP à scanner"
                    className="mx-auto rounded border border-slate-700 bg-white p-2"
                    width={220}
                    height={220}
                  />
                ) : null}
                <p className="text-xs text-slate-300">
                  Clé manuelle: <code>{totpSetup.manual_entry_key}</code>
                </p>
                <a
                  href={totpSetup.otpauth_uri}
                  className="text-xs underline text-cyan-300"
                >
                  Ouvrir dans l&apos;app d&apos;authentification
                </a>
                <input
                  type="text"
                  value={totpEnableCode}
                  onChange={(event) => setTotpEnableCode(event.target.value)}
                  placeholder="Code à 6 chiffres"
                  className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                />
                <button
                  type="submit"
                  className="btn btn-primary w-full"
                  disabled={submitting || !totpEnableCode.trim()}
                >
                  Activer 2FA
                </button>
              </form>
            )}
            {totpEnabled && (
              <p className="text-xs text-slate-400 mb-2">
                Gestion OTP avancée dans{" "}
                <Link href="/settings" className="underline text-cyan-300">
                  Paramètres
                </Link>
                .
              </p>
            )}
            <button
              type="button"
              className="btn btn-neutral w-full"
              onClick={onLogout}
              disabled={submitting}
            >
              {submitting ? "Déconnexion…" : "Déconnexion"}
            </button>
          </>
        ) : mfaToken ? (
          <form onSubmit={onVerifyMfa} className="space-y-2">
            <label>
              <span className="field-label">Code MFA</span>
              <input
                type="text"
                value={otpCode}
                onChange={(event) => setOtpCode(event.target.value)}
                placeholder="123456"
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700 mb-2"
                inputMode="numeric"
                pattern="[0-9]{6}"
                autoComplete="one-time-code"
              />
            </label>
            <button
              type="submit"
              className="btn btn-primary w-full"
              disabled={submitting || otpCode.trim().length < 6}
            >
              {submitting ? "Vérification…" : "Valider le code"}
            </button>
          </form>
        ) : (
          <form onSubmit={onSubmit} className="space-y-2">
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
            <button
              type="submit"
              className="btn btn-primary w-full"
              disabled={submitting || !username.trim() || !password}
            >
              {submitting ? "Connexion…" : "Connexion"}
            </button>
          </form>
        )}
      </div>
    </>
  ) : null;

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
      {authModal && typeof document !== "undefined"
        ? createPortal(authModal, document.body)
        : null}
    </div>
  );
}
