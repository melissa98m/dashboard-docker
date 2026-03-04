"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, apiJson } from "../../lib/api-client";
import { useAuth } from "../../contexts/auth-context";
import { useNotifications } from "../../components/notifications";

type MetricType = "cpu_percent" | "ram_mb" | "ram_percent";

interface AlertRule {
  id: number;
  container_id: string;
  container_name: string;
  metric_type: MetricType;
  threshold: number;
  cooldown_seconds: number;
  debounce_samples: number;
}

interface ContainerOption {
  id: string;
  name: string;
}

const metricLabels: Record<MetricType, string> = {
  cpu_percent: "CPU %",
  ram_mb: "RAM MB",
  ram_percent: "RAM %",
};

async function fetchContainersWithRetry(
  maxRetries = 2
): Promise<ContainerOption[]> {
  let lastError: Error | null = null;
  let delayMs = 300;
  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    try {
      return await apiJson<ContainerOption[]>("/api/containers");
    } catch (error) {
      lastError =
        error instanceof Error ? error : new Error("Erreur de chargement");
      if (attempt === maxRetries) break;
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      delayMs *= 2;
    }
  }
  throw lastError ?? new Error("Erreur de chargement");
}

export default function AlertsRulesPage() {
  const { isAdmin } = useAuth();
  const notify = useNotifications();
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [containers, setContainers] = useState<ContainerOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [reloadingContainers, setReloadingContainers] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [containerId, setContainerId] = useState("");
  const [metricType, setMetricType] = useState<MetricType>("cpu_percent");
  const [threshold, setThreshold] = useState("80");
  const [cooldownSeconds, setCooldownSeconds] = useState("300");
  const [debounceSamples, setDebounceSamples] = useState("1");
  const [restartingRuleId, setRestartingRuleId] = useState<number | null>(null);

  const loadData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const [rulesData, containersData] = await Promise.all([
        apiJson<AlertRule[]>("/api/alerts/rules"),
        fetchContainersWithRetry(),
      ]);
      setRules(rulesData);
      setContainers(containersData);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void loadData(false);
  }, []);

  const reloadContainers = async () => {
    setReloadingContainers(true);
    try {
      setContainers(await fetchContainersWithRetry());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setReloadingContainers(false);
    }
  };

  const onCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      const selectedContainer = containers.find(
        (container) => container.id === containerId
      );
      await apiFetch("/api/alerts/rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          container_id: containerId,
          container_name: selectedContainer?.name || containerId,
          metric_type: metricType,
          threshold: Number(threshold),
          cooldown_seconds: Number(cooldownSeconds),
          debounce_samples: Number(debounceSamples),
          enabled: true,
        }),
      });
      setContainerId("");
      setMetricType("cpu_percent");
      setThreshold("80");
      setCooldownSeconds("300");
      setDebounceSamples("1");
      await loadData(true);
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Erreur");
    }
  };

  const onDelete = async (id: number) => {
    try {
      await apiFetch(`/api/alerts/rules/${id}`, {
        method: "DELETE",
      });
      await loadData(true);
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Erreur");
    }
  };

  const onRestartContainer = async (rule: AlertRule) => {
    setRestartingRuleId(rule.id);
    try {
      await apiFetch(`/api/alerts/rules/${rule.id}/restart-container`, {
        method: "POST",
      });
      notify.success(`Container ${rule.container_name} redemarre`);
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Erreur");
    } finally {
      setRestartingRuleId(null);
    }
  };

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">Règles d&apos;alertes</h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void loadData(true)}
            disabled={loading || refreshing}
            className="btn btn-neutral px-3 py-1.5 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {refreshing
              ? "Rafraîchissement…"
              : loading
                ? "Chargement…"
                : "Rafraîchir"}
          </button>
          <div className="top-nav">
            <Link href="/alerts/history">Historique</Link>
            <Link href="/alerts">Accueil alertes</Link>
          </div>
        </div>
      </div>

      {isAdmin && (
      <section className="panel">
        <h2 className="font-semibold mb-3">Créer une règle</h2>
        <form onSubmit={onCreate} className="space-y-3">
          <label>
            <span className="field-label">Conteneur cible</span>
            <select
              value={containerId}
              onChange={(e) => setContainerId(e.target.value)}
              required
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            >
              <option value="" disabled>
                Choisir un conteneur
              </option>
              {containers.map((container) => (
                <option key={container.id} value={container.id}>
                  {container.name} ({container.id})
                </option>
              ))}
            </select>
          </label>
          {containers.length === 0 && (
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-amber-300">
                Aucun conteneur disponible.
              </p>
              <button
                type="button"
                onClick={() => void reloadContainers()}
                disabled={reloadingContainers}
                className="btn btn-neutral px-3 py-1 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {reloadingContainers ? "Chargement…" : "Rafraîchir la liste"}
              </button>
            </div>
          )}
          <label>
            <span className="field-label">Métrique</span>
            <select
              value={metricType}
              onChange={(e) => setMetricType(e.target.value as MetricType)}
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            >
              <option value="cpu_percent">CPU %</option>
              <option value="ram_mb">RAM MB</option>
              <option value="ram_percent">RAM %</option>
            </select>
          </label>
          <label>
            <span className="field-label">Seuil</span>
            <input
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              placeholder="Seuil"
              type="number"
              min="0"
              step="0.01"
              required
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            />
          </label>
          <label>
            <span className="field-label">Cooldown (secondes)</span>
            <input
              value={cooldownSeconds}
              onChange={(e) => setCooldownSeconds(e.target.value)}
              placeholder="Cooldown (secondes)"
              type="number"
              min="1"
              required
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            />
          </label>
          <label>
            <span className="field-label">Échantillons debounce</span>
            <input
              value={debounceSamples}
              onChange={(e) => setDebounceSamples(e.target.value)}
              placeholder="Echantillons debounce"
              type="number"
              min="1"
              max="20"
              required
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            />
          </label>
          <button type="submit" className="btn btn-success">
            Ajouter
          </button>
        </form>
      </section>
      )}

      <section className="panel">
        <h2 className="font-semibold mb-3">Règles actives</h2>
        {loading && <p>Chargement…</p>}
        {error && (
          <div className="space-y-2">
            <p className="text-red-400">Erreur : {error}</p>
            <button
              type="button"
              onClick={() => void loadData(false)}
              className="btn btn-neutral px-3 py-1.5 text-sm"
            >
              Réessayer
            </button>
          </div>
        )}
        {!loading && !error && rules.length === 0 && (
          <p className="text-slate-400">Aucune règle.</p>
        )}
        <ul className="space-y-2">
          {rules.map((rule) => (
            <li
              key={rule.id}
              className="entity-card flex items-center justify-between gap-2"
            >
              <div>
                <p className="font-medium">{rule.container_name}</p>
                <p className="text-xs text-slate-400">
                  {rule.container_id} · {metricLabels[rule.metric_type]} ≥{" "}
                  {rule.threshold} · cooldown {rule.cooldown_seconds}s ·
                  debounce {rule.debounce_samples}
                </p>
              </div>
              {isAdmin && (
                <>
                  <button
                    onClick={() => void onRestartContainer(rule)}
                    disabled={restartingRuleId === rule.id}
                    className="btn btn-warn px-3 py-1 text-xs disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {restartingRuleId === rule.id
                      ? "Redémarrage…"
                      : "Redémarrer le conteneur"}
                  </button>
                  <button
                    onClick={() => void onDelete(rule.id)}
                    className="btn btn-danger px-3 py-1 text-xs"
                  >
                    Supprimer
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
