"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, apiJson } from "../lib/api-client";
import { useAuth } from "../contexts/auth-context";
import { useNotifications } from "../components/notifications";

interface SecurityStatus {
  write_auth_configured: boolean;
  read_auth_enforced: boolean;
  read_auth_configured: boolean;
  sse_max_connections: number;
  alert_engine_enabled: boolean;
  alert_engine_running: boolean;
  alert_engine_last_cycle_at: string | null;
  alert_engine_last_success_at: string | null;
  alert_engine_consecutive_errors: number;
  alert_engine_last_error_reason: string | null;
  alert_engine_last_error_at: string | null;
  alert_poll_seconds: number;
  event_watcher_enabled: boolean;
  event_watcher_running: boolean;
  ntfy_configured: boolean;
  email_configured: boolean;
  restart_action_enabled: boolean;
  restart_action_ttl_seconds: number;
  restart_token_rate_limit_window_seconds: number;
  restart_token_rate_limit_max_attempts: number;
  audit_retention_days: number;
  audit_retention_auto_enabled: boolean;
  audit_retention_running: boolean;
  audit_retention_last_cycle_at: string | null;
  audit_retention_last_success_at: string | null;
  audit_retention_consecutive_errors: number;
  audit_retention_last_error_reason: string | null;
  audit_retention_last_error_at: string | null;
  audit_retention_poll_seconds: number;
  log_snapshot_redaction_enabled: boolean;
  log_snapshot_redaction_default_rules: string[];
  log_snapshot_redaction_extra_rules_count: number;
  runtime_config_loaded_at: string;
}

interface DependenciesHealth {
  ok: boolean;
  checks: {
    docker: { ok: boolean; detail: string };
    sqlite: { ok: boolean; detail: string };
  };
}

interface RuntimeSettings {
  sse_max_connections: number;
  alert_engine_enabled: boolean;
  alert_poll_seconds: number;
  restart_action_ttl_seconds: number;
  restart_token_rate_limit_window_seconds: number;
  restart_token_rate_limit_max_attempts: number;
  audit_retention_days: number;
  audit_retention_auto_enabled: boolean;
  audit_retention_poll_seconds: number;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

function formatTimestamp(value: string | null): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "n/a";
  return parsed.toLocaleString();
}

type ServiceHealth = "healthy" | "warning" | "unknown";

function computeServiceHealth(params: {
  enabled: boolean;
  running: boolean;
  lastSuccessAt: string | null;
  consecutiveErrors: number;
  pollSeconds: number;
}): ServiceHealth {
  const { enabled, running, lastSuccessAt, consecutiveErrors, pollSeconds } = params;
  if (!enabled) return "unknown";
  if (!running || consecutiveErrors > 0) return "warning";
  if (!lastSuccessAt) return "warning";

  const parsed = new Date(lastSuccessAt);
  if (Number.isNaN(parsed.getTime())) return "warning";
  const ageSeconds = Math.floor((Date.now() - parsed.getTime()) / 1000);
  const staleThreshold = Math.max(60, pollSeconds * 3);
  return ageSeconds > staleThreshold ? "warning" : "healthy";
}

function StateBadge({ active }: { active: boolean }) {
  return (
    <span
      className={
        active
          ? "inline-block px-2 py-1 text-xs rounded bg-emerald-600/30 text-emerald-300"
          : "inline-block px-2 py-1 text-xs rounded bg-amber-600/30 text-amber-300"
      }
    >
      {active ? "ON" : "OFF"}
    </span>
  );
}

function HealthBadge({ health }: { health: ServiceHealth }) {
  if (health === "healthy") {
    return (
      <span className="inline-block px-2 py-1 text-xs rounded bg-emerald-600/30 text-emerald-300">
        HEALTHY
      </span>
    );
  }
  if (health === "warning") {
    return (
      <span className="inline-block px-2 py-1 text-xs rounded bg-amber-600/30 text-amber-300">
        WARNING
      </span>
    );
  }
  return (
    <span className="inline-block px-2 py-1 text-xs rounded bg-slate-600/30 text-slate-300">
      UNKNOWN
    </span>
  );
}

type GlobalHealthStatus = "healthy" | "warning" | "degraded";

function computeGlobalHealth(params: {
  depsOk: boolean;
  alertHealth: ServiceHealth;
  auditRetentionHealth: ServiceHealth;
}): GlobalHealthStatus {
  const { depsOk, alertHealth, auditRetentionHealth } = params;
  if (!depsOk) return "degraded";
  if (alertHealth === "warning" || auditRetentionHealth === "warning") return "warning";
  return "healthy";
}

function GlobalHealthBadge({ status }: { status: GlobalHealthStatus }) {
  if (status === "healthy") {
    return (
      <span className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-emerald-600/25 text-emerald-300 border border-emerald-500/40">
        <span className="size-2 rounded-full bg-emerald-400 animate-pulse" aria-hidden />
        Opérationnel
      </span>
    );
  }
  if (status === "warning") {
    return (
      <span className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-amber-600/25 text-amber-300 border border-amber-500/40">
        <span className="size-2 rounded-full bg-amber-400" aria-hidden />
        Dégradé partiel
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-red-600/25 text-red-300 border border-red-500/40">
      <span className="size-2 rounded-full bg-red-400" aria-hidden />
      Problèmes critiques
    </span>
  );
}

function DepCheckRow({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean;
  detail: string;
}) {
  return (
    <div className="entity-card flex items-center justify-between gap-4">
      <span className="truncate">{label}</span>
      <div className="flex items-center gap-2 shrink-0 min-w-0">
        <span className="text-xs text-slate-400 truncate max-w-[10rem] sm:max-w-[16rem]" title={detail}>
          {detail}
        </span>
        <span
          className={
            ok
              ? "inline-block px-2 py-1 text-xs rounded bg-emerald-600/30 text-emerald-300 shrink-0"
              : "inline-block px-2 py-1 text-xs rounded bg-red-600/30 text-red-300 shrink-0"
          }
        >
          {ok ? "OK" : "KO"}
        </span>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const notify = useNotifications();
  const { me } = useAuth();
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [deps, setDeps] = useState<DependenciesHealth | null>(null);
  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettings | null>(null);
  const [form, setForm] = useState<RuntimeSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [newRole, setNewRole] = useState<"viewer" | "admin">("viewer");
  const [createUserSubmitting, setCreateUserSubmitting] = useState(false);
  const [createUserError, setCreateUserError] = useState<string | null>(null);

  const syncForm = (nextValues: RuntimeSettings) => {
    setRuntimeSettings(nextValues);
    setForm(nextValues);
  };

  useEffect(() => {
    const load = async () => {
      try {
        const [statusData, depsData, runtimeData] = await Promise.all([
          apiJson<SecurityStatus>("/api/system/security-status"),
          apiJson<DependenciesHealth>("/api/system/health/deps"),
          apiJson<RuntimeSettings>("/api/system/runtime-settings"),
        ]);
        setStatus(statusData);
        setDeps(depsData);
        syncForm(runtimeData);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur");
      }
    };
    void load();
  }, []);

  const onSave = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form) return;
    setSaving(true);
    try {
      await apiFetch("/api/system/runtime-settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const [statusData, runtimeData] = await Promise.all([
        apiJson<SecurityStatus>("/api/system/security-status"),
        apiJson<RuntimeSettings>("/api/system/runtime-settings"),
      ]);
      setStatus(statusData);
      syncForm(runtimeData);
      notify.success("Parametres enregistres");
      setError(null);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Erreur";
      setError(message);
      notify.error(message);
    } finally {
      setSaving(false);
    }
  };

  const onReset = () => {
    if (!runtimeSettings) return;
    setForm(runtimeSettings);
  };

  const onCreateUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreateUserError(null);
    const username = newUsername.trim();
    if (!username) {
      setCreateUserError("Nom d'utilisateur requis.");
      return;
    }
    if (newPassword.length < 12) {
      setCreateUserError("Mot de passe : minimum 12 caractères, lettres et chiffres.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setCreateUserError("La confirmation du mot de passe ne correspond pas.");
      return;
    }
    const hasAlpha = /[a-zA-Z]/.test(newPassword);
    const hasDigit = /\d/.test(newPassword);
    if (!hasAlpha || !hasDigit) {
      setCreateUserError("Mot de passe : lettres et chiffres requis.");
      return;
    }
    setCreateUserSubmitting(true);
    try {
      await apiFetch("/api/auth/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password: newPassword,
          role: newRole,
        }),
      });
      setNewUsername("");
      setNewPassword("");
      setConfirmPassword("");
      notify.success(`Utilisateur ${username} créé.`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erreur";
      setCreateUserError(msg);
      notify.error(msg);
    } finally {
      setCreateUserSubmitting(false);
    }
  };

  if (error) {
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <p className="text-red-400">Erreur: {error}</p>
      </main>
    );
  }

  if (!status) {
    return <main className="page-shell p-4">Chargement…</main>;
  }

  const loadedAt = new Date(status.runtime_config_loaded_at);
  const now = new Date();
  const uptimeSeconds = Math.max(0, Math.floor((now.getTime() - loadedAt.getTime()) / 1000));
  const alertHealth = computeServiceHealth({
    enabled: status.alert_engine_enabled,
    running: status.alert_engine_running,
    lastSuccessAt: status.alert_engine_last_success_at,
    consecutiveErrors: status.alert_engine_consecutive_errors,
    pollSeconds: status.alert_poll_seconds,
  });
  const auditRetentionHealth = computeServiceHealth({
    enabled: status.audit_retention_auto_enabled,
    running: status.audit_retention_running,
    lastSuccessAt: status.audit_retention_last_success_at,
    consecutiveErrors: status.audit_retention_consecutive_errors,
    pollSeconds: status.audit_retention_poll_seconds,
  });
  const globalHealth = computeGlobalHealth({
    depsOk: deps?.ok ?? false,
    alertHealth,
    auditRetentionHealth,
  });

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">Parametres de securite</h1>
        <div className="top-nav">
          <Link href="/audit">Audit</Link>
          <Link href="/">Dashboard</Link>
        </div>
      </div>

      <section
        className={`panel space-y-4 border-2 ${
          globalHealth === "healthy"
            ? "border-emerald-500/30"
            : globalHealth === "warning"
              ? "border-amber-500/30"
              : "border-red-500/30"
        }`}
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="font-semibold text-lg">Santé globale</h2>
          <div className="flex flex-wrap items-center gap-4">
            <GlobalHealthBadge status={globalHealth} />
            <span className="text-sm text-slate-400">
              Uptime API · {formatDuration(uptimeSeconds)}
            </span>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-2">
            <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Dépendances
            </h3>
            {deps ? (
              <>
                <DepCheckRow
                  label="Docker"
                  ok={deps.checks.docker.ok}
                  detail={deps.checks.docker.detail ?? "n/a"}
                />
                <DepCheckRow
                  label="SQLite"
                  ok={deps.checks.sqlite.ok}
                  detail={deps.checks.sqlite.detail ?? "n/a"}
                />
              </>
            ) : (
              <p className="text-sm text-slate-500">Chargement…</p>
            )}
          </div>
          <div className="space-y-2">
            <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Services
            </h3>
            <div className="entity-card flex items-center justify-between">
              <span>Moteur d&apos;alertes</span>
              <HealthBadge health={alertHealth} />
            </div>
            <div className="entity-card flex items-center justify-between">
              <span>Purge retention audit</span>
              <HealthBadge health={auditRetentionHealth} />
            </div>
          </div>
        </div>
      </section>

      <section className="panel space-y-3">
        <div className="entity-card flex items-center justify-between">
          <span>Auth ecriture configuree</span>
          <StateBadge active={status.write_auth_configured} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Auth lecture imposee</span>
          <StateBadge active={status.read_auth_enforced} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Auth lecture configuree</span>
          <StateBadge active={status.read_auth_configured} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Moteur d&apos;alertes</span>
          <StateBadge active={status.alert_engine_enabled} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Moteur d&apos;alertes (etat runtime)</span>
          <StateBadge active={status.alert_engine_running} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Sante moteur d&apos;alertes</span>
          <HealthBadge health={alertHealth} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Event watcher (die/oom)</span>
          <StateBadge active={status.event_watcher_enabled} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Event watcher (etat runtime)</span>
          <StateBadge active={status.event_watcher_running} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>ntfy configure</span>
          <StateBadge active={status.ntfy_configured} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Email configure (Resend)</span>
          <StateBadge active={status.email_configured} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Liens signes pour redemarrage</span>
          <StateBadge active={status.restart_action_enabled} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Purge auto retention audit</span>
          <StateBadge active={status.audit_retention_auto_enabled} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Purge auto retention audit (etat runtime)</span>
          <StateBadge active={status.audit_retention_running} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Sante retention audit</span>
          <HealthBadge health={auditRetentionHealth} />
        </div>
        <div className="entity-card flex items-center justify-between">
          <span>Masquage snapshot logs</span>
          <StateBadge active={status.log_snapshot_redaction_enabled} />
        </div>
      </section>

      <section className="panel space-y-3">
        <h2 className="font-semibold">Parametres modifiables</h2>
        {!form ? (
          <p className="text-sm text-slate-400">Chargement des parametres...</p>
        ) : (
          <form className="space-y-3" onSubmit={onSave}>
            <label>
              <span className="field-label">Connexions SSE max</span>
              <input
                type="number"
                min={1}
                max={500}
                value={form.sse_max_connections}
                onChange={(e) =>
                  setForm({
                    ...form,
                    sse_max_connections: Number(e.target.value),
                  })
                }
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
              />
            </label>
            <label>
              <span className="field-label">Moteur d&apos;alertes active</span>
              <input
                type="checkbox"
                checked={form.alert_engine_enabled}
                onChange={(e) =>
                  setForm({
                    ...form,
                    alert_engine_enabled: e.target.checked,
                  })
                }
                className="h-4 w-4 accent-emerald-500"
              />
            </label>
            <label>
              <span className="field-label">Intervalle polling alertes (s)</span>
              <input
                type="number"
                min={1}
                max={300}
                value={form.alert_poll_seconds}
                onChange={(e) =>
                  setForm({
                    ...form,
                    alert_poll_seconds: Number(e.target.value),
                  })
                }
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
              />
            </label>
            <label>
              <span className="field-label">TTL token redemarrage (s)</span>
              <input
                type="number"
                min={30}
                max={3600}
                value={form.restart_action_ttl_seconds}
                onChange={(e) =>
                  setForm({
                    ...form,
                    restart_action_ttl_seconds: Number(e.target.value),
                  })
                }
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
              />
            </label>
            <label>
              <span className="field-label">Fenetre limite token redemarrage (s)</span>
              <input
                type="number"
                min={10}
                max={3600}
                value={form.restart_token_rate_limit_window_seconds}
                onChange={(e) =>
                  setForm({
                    ...form,
                    restart_token_rate_limit_window_seconds: Number(e.target.value),
                  })
                }
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
              />
            </label>
            <label>
              <span className="field-label">Max tentatives token redemarrage</span>
              <input
                type="number"
                min={1}
                max={1000}
                value={form.restart_token_rate_limit_max_attempts}
                onChange={(e) =>
                  setForm({
                    ...form,
                    restart_token_rate_limit_max_attempts: Number(e.target.value),
                  })
                }
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
              />
            </label>
            <label>
              <span className="field-label">Retention audit (jours)</span>
              <input
                type="number"
                min={1}
                max={3650}
                value={form.audit_retention_days}
                onChange={(e) =>
                  setForm({
                    ...form,
                    audit_retention_days: Number(e.target.value),
                  })
                }
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
              />
            </label>
            <label>
              <span className="field-label">Purge auto retention audit active</span>
              <input
                type="checkbox"
                checked={form.audit_retention_auto_enabled}
                onChange={(e) =>
                  setForm({
                    ...form,
                    audit_retention_auto_enabled: e.target.checked,
                  })
                }
                className="h-4 w-4 accent-emerald-500"
              />
            </label>
            <label>
              <span className="field-label">Intervalle purge retention audit (s)</span>
              <input
                type="number"
                min={10}
                max={604800}
                value={form.audit_retention_poll_seconds}
                onChange={(e) =>
                  setForm({
                    ...form,
                    audit_retention_poll_seconds: Number(e.target.value),
                  })
                }
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
              />
            </label>
            <div className="flex items-center gap-2">
              <button
                type="submit"
                disabled={saving}
                className="btn btn-success disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {saving ? "Enregistrement..." : "Enregistrer"}
              </button>
              <button type="button" onClick={onReset} className="btn btn-neutral">
                Reinitialiser
              </button>
            </div>
          </form>
        )}
      </section>

      {me?.role === "admin" && (
        <section className="panel space-y-3">
          <h2 className="font-semibold">Créer un utilisateur</h2>
          <p className="text-xs text-slate-400">
            Minimum 12 caractères, lettres et chiffres. Réservé aux admins.
          </p>
          <form onSubmit={onCreateUser} className="space-y-3">
            {createUserError && (
              <p className="text-sm text-red-400">{createUserError}</p>
            )}
            <label>
              <span className="field-label">Nom d&apos;utilisateur</span>
              <input
                type="text"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                placeholder="alice"
                minLength={3}
                maxLength={120}
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
                autoComplete="off"
              />
            </label>
            <label>
              <span className="field-label">Mot de passe</span>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="12+ caractères, lettres et chiffres"
                minLength={12}
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
                autoComplete="new-password"
              />
            </label>
            <label>
              <span className="field-label">Confirmer le mot de passe</span>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Saisir à nouveau"
                minLength={12}
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
                autoComplete="new-password"
              />
            </label>
            <label>
              <span className="field-label">Rôle</span>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as "viewer" | "admin")}
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
              >
                <option value="viewer">Viewer (lecture seule)</option>
                <option value="admin">Admin (lecture + écriture)</option>
              </select>
            </label>
            <button
              type="submit"
              disabled={createUserSubmitting}
              className="btn btn-success disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {createUserSubmitting ? "Création..." : "Créer l&apos;utilisateur"}
            </button>
          </form>
        </section>
      )}

      <section className="panel space-y-2 text-sm">
        <h2 className="font-semibold mb-2">Détails techniques</h2>
        <p>Connexions SSE max: {status.sse_max_connections}</p>
        <p>Intervalle polling alertes: {status.alert_poll_seconds}s</p>
        <p>TTL token redemarrage: {status.restart_action_ttl_seconds}s</p>
        <p>
          Limite token redemarrage: {status.restart_token_rate_limit_max_attempts} tentatives /{" "}
          {status.restart_token_rate_limit_window_seconds}s
        </p>
        <p>Retention audit: {status.audit_retention_days} jours</p>
        <p>Intervalle purge retention audit: {status.audit_retention_poll_seconds}s</p>
        <p>Dernier cycle moteur alertes: {formatTimestamp(status.alert_engine_last_cycle_at)}</p>
        <p>Dernier succes moteur alertes: {formatTimestamp(status.alert_engine_last_success_at)}</p>
        <p>Erreurs consecutives moteur alertes: {status.alert_engine_consecutive_errors}</p>
        <p>Derniere erreur moteur alertes: {status.alert_engine_last_error_reason ?? "n/a"}</p>
        <p>Date derniere erreur moteur alertes: {formatTimestamp(status.alert_engine_last_error_at)}</p>
        <p>Dernier cycle retention audit: {formatTimestamp(status.audit_retention_last_cycle_at)}</p>
        <p>Dernier succes retention audit: {formatTimestamp(status.audit_retention_last_success_at)}</p>
        <p>Erreurs consecutives retention audit: {status.audit_retention_consecutive_errors}</p>
        <p>Derniere erreur retention audit: {status.audit_retention_last_error_reason ?? "n/a"}</p>
        <p>Date derniere erreur retention audit: {formatTimestamp(status.audit_retention_last_error_at)}</p>
        <p>Config chargee le: {new Date(status.runtime_config_loaded_at).toLocaleString()}</p>
        <p>Uptime API (approx): {formatDuration(uptimeSeconds)}</p>
        <p>
          Regles de masquage par defaut:{" "}
          {status.log_snapshot_redaction_default_rules.length > 0
            ? status.log_snapshot_redaction_default_rules.join(", ")
            : "aucune"}
        </p>
        <p>Nombre de regles de masquage additionnelles: {status.log_snapshot_redaction_extra_rules_count}</p>
      </section>
    </main>
  );
}
