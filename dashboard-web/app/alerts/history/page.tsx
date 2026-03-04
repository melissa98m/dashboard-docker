"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, apiJson } from "../../lib/api-client";
import { useAuth } from "../../contexts/auth-context";
import { useNotifications } from "../../components/notifications";

type MetricType = "cpu_percent" | "ram_mb" | "ram_percent";

interface ContainerOption {
  id: string;
  name: string;
}

interface AlertHistoryItem {
  id: number;
  rule_id: number | null;
  container_id: string | null;
  container_name: string | null;
  metric_type: MetricType | null;
  value: number | null;
  triggered_by: string;
  created_at: string;
  can_restart: boolean;
}

interface AlertHistoryResponse {
  items: AlertHistoryItem[];
  total: number;
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

export default function AlertsHistoryPage() {
  const notify = useNotifications();
  const [history, setHistory] = useState<AlertHistoryItem[]>([]);
  const [containers, setContainers] = useState<ContainerOption[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyContainerFilter, setHistoryContainerFilter] = useState("");
  const [historyMetricFilter, setHistoryMetricFilter] = useState<
    MetricType | ""
  >("");
  const [historyTriggeredByFilter, setHistoryTriggeredByFilter] = useState<
    "all" | "manual" | "alert-engine"
  >("all");
  const [historySinceHours, setHistorySinceHours] = useState("24");
  const [historySort, setHistorySort] = useState<
    "created_at_desc" | "created_at_asc"
  >("created_at_desc");
  const [error, setError] = useState<string | null>(null);
  const [restartingRuleId, setRestartingRuleId] = useState<number | null>(null);
  const historyPageSize = 20;

  const buildHistoryUrl = (offset: number) => {
    const params = new URLSearchParams({
      limit: String(historyPageSize),
      offset: String(offset),
    });
    if (historyContainerFilter)
      params.set("container_id", historyContainerFilter);
    if (historyMetricFilter) params.set("metric_type", historyMetricFilter);
    if (historyTriggeredByFilter !== "all")
      params.set("triggered_by", historyTriggeredByFilter);
    if (historySinceHours.trim())
      params.set("since_hours", historySinceHours.trim());
    params.set("sort", historySort);
    return `/api/alerts/history?${params.toString()}`;
  };

  const loadHistory = async ({ reset }: { reset: boolean }) => {
    setHistoryLoading(true);
    try {
      const targetOffset = reset ? 0 : history.length;
      const payload = await apiJson<AlertHistoryResponse>(
        buildHistoryUrl(targetOffset)
      );
      const page = payload.items;
      const nextItems = reset ? page : [...history, ...page];
      setHistory(nextItems);
      setHistoryTotal(payload.total);
      setHistoryHasMore(nextItems.length < payload.total);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        setContainers(await fetchContainersWithRetry());
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur de chargement");
      }
    };
    void load();
  }, []);

  useEffect(() => {
    void loadHistory({ reset: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    historyContainerFilter,
    historyMetricFilter,
    historyTriggeredByFilter,
    historySinceHours,
    historySort,
  ]);

  const onRestartFromHistory = async (item: AlertHistoryItem) => {
    if (item.rule_id == null) return;
    setRestartingRuleId(item.rule_id);
    const label =
      item.container_name || item.container_id || `rule #${item.rule_id}`;
    try {
      await apiFetch(`/api/alerts/rules/${item.rule_id}/restart-container`, {
        method: "POST",
      });
      notify.success(`Container ${label} redemarre`);
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Erreur");
    } finally {
      setRestartingRuleId(null);
    }
  };

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">
          Historique des alertes
        </h1>
        <div className="top-nav">
          <Link href="/alerts/rules">Règles</Link>
          <Link href="/alerts">Accueil alertes</Link>
        </div>
      </div>

      <section className="panel">
        <p className="text-xs text-slate-400 mb-2">Resultats: {historyTotal}</p>
        <div className="grid gap-2 mb-3">
          <label>
            <span className="field-label">Filtre conteneur</span>
            <select
              value={historyContainerFilter}
              onChange={(event) =>
                setHistoryContainerFilter(event.target.value)
              }
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            >
              <option value="">Tous les conteneurs</option>
              {containers.map((container) => (
                <option key={container.id} value={container.id}>
                  {container.name} ({container.id})
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">Filtre métrique</span>
            <select
              value={historyMetricFilter}
              onChange={(event) =>
                setHistoryMetricFilter(event.target.value as MetricType | "")
              }
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            >
              <option value="">Toutes les métriques</option>
              <option value="cpu_percent">CPU %</option>
              <option value="ram_mb">RAM MB</option>
              <option value="ram_percent">RAM %</option>
            </select>
          </label>
          <label>
            <span className="field-label">Origine</span>
            <select
              value={historyTriggeredByFilter}
              onChange={(event) =>
                setHistoryTriggeredByFilter(
                  event.target.value as "all" | "manual" | "alert-engine"
                )
              }
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            >
              <option value="all">Toutes les origines</option>
              <option value="manual">Manuel</option>
              <option value="alert-engine">Alert engine</option>
            </select>
          </label>
          <label>
            <span className="field-label">Fenêtre en heures</span>
            <input
              value={historySinceHours}
              onChange={(event) => setHistorySinceHours(event.target.value)}
              placeholder="Fenêtre heures (ex: 24)"
              type="number"
              min="1"
              max={24 * 30}
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            />
          </label>
          <label>
            <span className="field-label">Tri</span>
            <select
              value={historySort}
              onChange={(event) =>
                setHistorySort(
                  event.target.value as "created_at_desc" | "created_at_asc"
                )
              }
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            >
              <option value="created_at_desc">
                Plus recentes d&apos;abord
              </option>
              <option value="created_at_asc">
                Plus anciennes d&apos;abord
              </option>
            </select>
          </label>
        </div>

        {error && <p className="text-red-400">Erreur : {error}</p>}
        {historyLoading && history.length === 0 && <p>Chargement…</p>}
        {history.length === 0 && (
          <p className="text-slate-400">Aucun déclenchement récent.</p>
        )}
        <ul className="space-y-2">
          {history.map((item) => (
            <li
              key={item.id}
              className="entity-card flex items-center justify-between gap-2"
            >
              <div>
                <p className="font-medium">
                  {item.container_name ||
                    item.container_id ||
                    "Container inconnu"}
                </p>
                <p className="text-xs text-slate-400">
                  {item.metric_type ? metricLabels[item.metric_type] : "metric"}{" "}
                  · valeur {item.value != null ? item.value.toFixed(2) : "n/a"}{" "}
                  · {new Date(item.created_at).toLocaleString()}
                </p>
              </div>
              {isAdmin && (
                <button
                  onClick={() => void onRestartFromHistory(item)}
                  disabled={
                    !item.can_restart ||
                    item.rule_id == null ||
                    restartingRuleId === item.rule_id
                  }
                  className="btn btn-warn px-3 py-1 text-xs disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {item.rule_id != null && restartingRuleId === item.rule_id
                    ? "Redémarrage…"
                    : "Redémarrer le conteneur"}
                </button>
              )}
            </li>
          ))}
        </ul>
        {historyHasMore && (
          <button
            onClick={() => void loadHistory({ reset: false })}
            disabled={historyLoading}
            className="btn btn-neutral mt-3 px-3 py-1 text-xs disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {historyLoading ? "Chargement…" : "Voir plus"}
          </button>
        )}
      </section>
    </main>
  );
}
