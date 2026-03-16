"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError, apiJson, streamSse } from "../../lib/api-client";
import { LogSnapshot } from "../../components/log-snapshot";
import {
  STATS_RANGE_OPTIONS,
  StatsCharts,
  type StatsDataPoint,
  type StatsRangeId,
} from "./components/stats-charts";

interface ContainerDetail {
  id: string;
  name: string;
  image: string;
  status: string;
  uptime_seconds: number | null;
  finished_at: string | null;
  exit_code: number | null;
  oom_killed: boolean | null;
  health_status: string | null;
  last_down_reason: string | null;
  last_logs: string[];
  linked_images: LinkedImage[];
  mounted_volumes: MountedVolume[];
}

interface LinkedImage {
  id: string;
  display_name: string;
  tags: string[];
}

interface MountedVolume {
  type: string;
  name: string | null;
  source: string | null;
  destination: string;
  read_only: boolean | null;
}

interface StatsPayload {
  cpu_percent: number;
  memory_mb: number;
  memory_percent: number;
}
type StatsStreamStatus =
  | "idle"
  | "connecting"
  | "live"
  | "reconnecting"
  | "error";

function formatUptime(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

function formatStreamStatus(status: StatsStreamStatus): string {
  if (status === "live") return "en direct";
  if (status === "connecting") return "connexion…";
  if (status === "reconnecting") return "reconnexion…";
  if (status === "error") return "erreur";
  return "inactif";
}

export default function ContainerDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const [detail, setDetail] = useState<ContainerDetail | null>(null);
  const [stats, setStats] = useState<StatsPayload>({
    cpu_percent: 0,
    memory_mb: 0,
    memory_percent: 0,
  });
  const [statsHistory, setStatsHistory] = useState<StatsDataPoint[]>([]);
  const [statsRange, setStatsRange] = useState<StatsRangeId>("2m");
  const [error, setError] = useState<string | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [statsStreamStatus, setStatsStreamStatus] =
    useState<StatsStreamStatus>("idle");
  const containerId = useMemo(() => params.id, [params.id]);
  const statsRangeConfig = useMemo(
    () =>
      STATS_RANGE_OPTIONS.find((o) => o.id === statsRange) ??
      STATS_RANGE_OPTIONS[0],
    [statsRange]
  );

  const loadDetail = useCallback(async () => {
    setError(null);
    try {
      const data = await apiJson<ContainerDetail>(
        `/api/containers/${encodeURIComponent(containerId)}?tail=100`
      );
      setDetail(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    }
  }, [containerId]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  useEffect(() => {
    setStatsHistory([]);
    setStats({
      cpu_percent: 0,
      memory_mb: 0,
      memory_percent: 0,
    });
  }, [containerId]);

  useEffect(() => {
    const timer = setInterval(() => {
      void loadDetail();
    }, 15000);
    return () => clearInterval(timer);
  }, [loadDetail]);

  useEffect(() => {
    setStatsError(null);
    if (detail?.status !== "running") {
      setStatsStreamStatus("idle");
      return;
    }
    setStatsStreamStatus("connecting");

    let stopped = false;
    let stopStream: (() => void) | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    const scheduleReconnect = (attempt: number) => {
      if (retryTimer) clearTimeout(retryTimer);
      const retryMs = Math.min(30000, 1000 * 2 ** Math.min(attempt, 5));
      setStatsStreamStatus("reconnecting");
      retryTimer = setTimeout(() => connect(attempt + 1), retryMs);
    };

    const connect = (attempt: number) => {
      if (stopped) return;
      setStatsStreamStatus(attempt === 0 ? "connecting" : "reconnecting");

      const query = new URLSearchParams({
        interval_ms: String(statsRangeConfig.intervalSec * 1000),
      });
      stopStream = streamSse(
        `/api/containers/${encodeURIComponent(containerId)}/stats?${query.toString()}`,
        {
          onEvent: (eventType, data) => {
            if (eventType === "stats") {
              const raw = data as Partial<StatsPayload> | null;
              const cpu = Number(raw?.cpu_percent);
              const memoryMb = Number(raw?.memory_mb);
              const memoryPercent = Number(raw?.memory_percent);
              if (
                !Number.isFinite(cpu) ||
                !Number.isFinite(memoryMb) ||
                !Number.isFinite(memoryPercent)
              ) {
                return;
              }
              const payload: StatsPayload = {
                cpu_percent: Math.max(0, cpu),
                memory_mb: Math.max(0, memoryMb),
                memory_percent: Math.max(0, Math.min(100, memoryPercent)),
              };
              setStats(payload);
              setStatsError(null);
              setStatsStreamStatus("live");
              const now = Date.now();
              setStatsHistory((prev) => {
                const point: StatsDataPoint = {
                  ts: now,
                  cpu_percent: payload.cpu_percent,
                  memory_mb: payload.memory_mb,
                  memory_percent: payload.memory_percent,
                };
                const next = [...prev, point];
                return next.length > statsRangeConfig.maxPoints
                  ? next.slice(-statsRangeConfig.maxPoints)
                  : next;
              });
            }
            if (eventType === "error") {
              setStatsError("Flux stats interrompu côté serveur.");
            }
          },
          onError: (err) => {
            if (stopped) return;
            setStatsError(err.message);
            if (err instanceof ApiClientError && err.status === 409) {
              setStatsError("Conteneur arrêté, stats live en pause.");
              setStatsStreamStatus("idle");
              void loadDetail();
              return;
            }
            const isRetriable =
              !(err instanceof ApiClientError) ||
              err.status === 429 ||
              err.status >= 500;
            if (!isRetriable) {
              setStatsStreamStatus("error");
              return;
            }
            scheduleReconnect(attempt);
          },
          onClose: () => {
            if (stopped) return;
            scheduleReconnect(attempt);
          },
        }
      );
    };

    connect(0);
    return () => {
      stopped = true;
      if (retryTimer) clearTimeout(retryTimer);
      stopStream?.();
      setStatsStreamStatus("idle");
    };
  }, [containerId, detail?.status, loadDetail, statsRangeConfig]);

  if (error) {
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
        <p className="text-red-400">Erreur : {error}</p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => void loadDetail()}
            className="btn btn-neutral px-4 py-2"
          >
            Réessayer
          </button>
          <Link href="/" className="btn btn-neutral px-4 py-2">
            Retour à la liste
          </Link>
        </div>
      </main>
    );
  }

  if (!detail) {
    return <main className="page-shell p-4">Chargement…</main>;
  }

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">{detail.name}</h1>
        <div className="top-nav">
          <Link href={`/containers/${encodeURIComponent(containerId)}/logs`}>
            Logs
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/commands`}
          >
            Commandes
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/workflows`}
          >
            Workflows
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/environment`}
          >
            Environnement
          </Link>
        </div>
      </div>

      <section className="panel">
        <h2 className="font-semibold">Vue générale</h2>
        <p className="text-slate-400 text-sm">{detail.image}</p>
        <p className="mt-2">
          Statut:{" "}
          <span
            className={
              detail.status === "running"
                ? "text-emerald-400"
                : "text-amber-400"
            }
          >
            {detail.status}
          </span>
          <span className="ml-2 text-slate-500">
            • uptime {formatUptime(detail.uptime_seconds)}
          </span>
        </p>
        {detail.finished_at && (
          <p className="text-xs text-slate-400 mt-1">
            Dernier arrêt: {new Date(detail.finished_at).toLocaleString()}
          </p>
        )}
        {detail.last_down_reason && (
          <p className="text-xs text-amber-300 mt-1 break-words">
            Raison down: {detail.last_down_reason}
          </p>
        )}
      </section>

      <section className="panel">
        <h2 className="font-semibold mb-2">Ressources liées</h2>
        <div className="space-y-3">
          <div>
            <p className="text-sm text-slate-300">Images</p>
            {detail.linked_images.length === 0 ? (
              <p className="text-xs text-slate-500 mt-1">Aucune image liée.</p>
            ) : (
              <ul className="mt-1 space-y-1 text-sm">
                {detail.linked_images.map((img) => (
                  <li key={img.id}>
                    <Link
                      href={`/images/${encodeURIComponent(img.id)}`}
                      className="text-sky-400 hover:underline"
                    >
                      {img.display_name}
                    </Link>
                    {img.tags.length > 0 && (
                      <span className="text-xs text-slate-500 ml-2">
                        ({img.tags.length} tag{img.tags.length > 1 ? "s" : ""})
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <p className="text-sm text-slate-300">Volumes / montages</p>
            {detail.mounted_volumes.length === 0 ? (
              <p className="text-xs text-slate-500 mt-1">Aucun montage.</p>
            ) : (
              <ul className="mt-1 space-y-1 text-sm">
                {detail.mounted_volumes.map((mount) => {
                  const key = `${mount.type}-${mount.destination}-${mount.source ?? mount.name ?? "none"}`;
                  return (
                    <li key={key}>
                      {mount.type === "volume" && mount.name ? (
                        <Link
                          href={`/volumes/${encodeURIComponent(mount.name)}`}
                          className="text-sky-400 hover:underline"
                        >
                          {mount.name}
                        </Link>
                      ) : (
                        <span className="text-slate-300">
                          {mount.source ?? "mount"}
                        </span>
                      )}
                      <span className="text-slate-500">
                        {" "}
                        → {mount.destination}
                      </span>
                      {mount.read_only === true && (
                        <span className="text-xs text-amber-300 ml-2">
                          (read-only)
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </section>

      <section className="panel">
        <h2 className="font-semibold mb-2">Stats live</h2>
        <p className="text-xs text-slate-500 mb-2" aria-live="polite">
          Stream: {formatStreamStatus(statsStreamStatus)}
        </p>
        {statsError ? (
          <p className="text-amber-400 text-sm">{statsError}</p>
        ) : (
          <>
            <p>CPU: {stats.cpu_percent.toFixed(2)}%</p>
            <p>
              RAM: {stats.memory_mb.toFixed(2)} MB (
              {stats.memory_percent.toFixed(2)}%)
            </p>
            <StatsCharts
              data={statsHistory}
              isRunning={detail.status === "running"}
              range={statsRange}
              onRangeChange={setStatsRange}
            />
          </>
        )}
      </section>

      <section className="panel">
        <h2 className="font-semibold mb-2">Diagnostic arrêt</h2>
        <p>Exit code: {detail.exit_code ?? "—"}</p>
        <p>
          OOM killed:{" "}
          {detail.oom_killed == null ? "—" : detail.oom_killed ? "yes" : "no"}
        </p>
        <p>Health: {detail.health_status ?? "—"}</p>
      </section>

      {detail.status !== "running" && detail.last_logs.length > 0 && (
        <section className="panel">
          <LogSnapshot
            lines={detail.last_logs}
            title="Derniers logs (avant arrêt)"
            subtitle="Snapshot capturé pour le diagnostic du dernier arrêt."
            maxHeightClassName="max-h-64"
          />
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/logs`}
            className="text-xs text-sky-400 hover:underline mt-2 inline-block"
          >
            Voir tous les logs →
          </Link>
        </section>
      )}

      <section className="panel">
        <h2 className="font-semibold mb-2">Fonctionnalités associées</h2>
        <div className="grid gap-3">
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/logs`}
            className="entity-card"
          >
            <p className="font-medium">Logs</p>
            <p className="text-xs muted">Snapshot + stream en temps reel.</p>
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/commands`}
            className="entity-card"
          >
            <p className="font-medium">Commandes</p>
            <p className="text-xs muted">
              Allowlist, scan et executions du conteneur.
            </p>
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/workflows`}
            className="entity-card"
          >
            <p className="font-medium">Workflows</p>
            <p className="text-xs muted">GitHub Actions (act) du conteneur.</p>
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/environment`}
            className="entity-card"
          >
            <p className="font-medium">Variables d&apos;environnement</p>
            <p className="text-xs muted">
              Edition du profil et application sur recreate.
            </p>
          </Link>
        </div>
      </section>
    </main>
  );
}
