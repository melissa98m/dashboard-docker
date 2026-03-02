"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiJson, streamSse } from "../../lib/api-client";
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
}

interface StatsPayload {
  cpu_percent: number;
  memory_mb: number;
  memory_percent: number;
}

function formatUptime(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
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
  const containerId = useMemo(() => params.id, [params.id]);
  const lastSampleTsRef = useRef<number>(0);
  const statsRangeRef = useRef(statsRange);
  statsRangeRef.current = statsRange;

  useEffect(() => {
    let isMounted = true;
    const loadDetail = async () => {
      try {
        const data = await apiJson<ContainerDetail>(
          `/api/containers/${encodeURIComponent(containerId)}?tail=100`
        );
        if (isMounted) setDetail(data);
      } catch (e) {
        if (isMounted) {
          setError(e instanceof Error ? e.message : "Erreur de chargement");
        }
      }
    };
    loadDetail();
    return () => {
      isMounted = false;
    };
  }, [containerId]);

  useEffect(() => {
    setStatsError(null);
    setStatsHistory([]);
    lastSampleTsRef.current = 0;
    const stop = streamSse(`/api/containers/${encodeURIComponent(containerId)}/stats`, {
      onEvent: (eventType, data) => {
        if (eventType === "stats") {
          const payload = data as StatsPayload;
          setStats(payload);
          const rangeConfig = STATS_RANGE_OPTIONS.find((o) => o.id === statsRangeRef.current) ?? STATS_RANGE_OPTIONS[0];
          const now = Date.now();
          const elapsedMs = now - lastSampleTsRef.current;
          const intervalMs = rangeConfig.intervalSec * 1000;
          if (lastSampleTsRef.current === 0 || elapsedMs >= intervalMs) {
            lastSampleTsRef.current = now;
            setStatsHistory((prev) => {
              const point: StatsDataPoint = {
                ts: now,
                cpu_percent: payload.cpu_percent,
                memory_mb: payload.memory_mb,
                memory_percent: payload.memory_percent,
              };
              const next = [...prev, point];
              return next.length > rangeConfig.maxPoints ? next.slice(-rangeConfig.maxPoints) : next;
            });
          }
        }
      },
      onError: (err) => setStatsError(err.message),
    });
    return stop;
  }, [containerId]);

  if (error) {
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <p className="text-red-400">Erreur: {error}</p>
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
          <Link href={`/containers/${encodeURIComponent(containerId)}/logs`}>Logs</Link>
          <Link href={`/containers/${encodeURIComponent(containerId)}/commands`}>Commandes</Link>
          <Link href={`/containers/${encodeURIComponent(containerId)}/environment`}>Environnement</Link>
        </div>
      </div>

      <section className="panel">
        <h2 className="font-semibold">Vue generale</h2>
        <p className="text-slate-400 text-sm">{detail.image}</p>
        <p className="mt-2">
          Statut:{" "}
          <span className={detail.status === "running" ? "text-emerald-400" : "text-amber-400"}>
            {detail.status}
          </span>
          <span className="ml-2 text-slate-500">• uptime {formatUptime(detail.uptime_seconds)}</span>
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
        <h2 className="font-semibold mb-2">Stats live</h2>
        {statsError ? (
          <p className="text-amber-400 text-sm">{statsError}</p>
        ) : (
          <>
            <p>CPU: {stats.cpu_percent.toFixed(2)}%</p>
            <p>RAM: {stats.memory_mb.toFixed(2)} MB ({stats.memory_percent.toFixed(2)}%)</p>
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
        <p>OOM killed: {detail.oom_killed == null ? "—" : detail.oom_killed ? "yes" : "no"}</p>
        <p>Health: {detail.health_status ?? "—"}</p>
      </section>

      <section className="panel">
        <h2 className="font-semibold mb-2">Fonctionnalites associees</h2>
        <div className="grid gap-3">
          <Link href={`/containers/${encodeURIComponent(containerId)}/logs`} className="entity-card">
            <p className="font-medium">Logs</p>
            <p className="text-xs muted">Snapshot + stream en temps reel.</p>
          </Link>
          <Link href={`/containers/${encodeURIComponent(containerId)}/commands`} className="entity-card">
            <p className="font-medium">Commandes</p>
            <p className="text-xs muted">Allowlist, scan et executions du conteneur.</p>
          </Link>
          <Link href={`/containers/${encodeURIComponent(containerId)}/environment`} className="entity-card">
            <p className="font-medium">Variables d&apos;environnement</p>
            <p className="text-xs muted">Edition du profil et application sur recreate.</p>
          </Link>
        </div>
      </section>
    </main>
  );
}
