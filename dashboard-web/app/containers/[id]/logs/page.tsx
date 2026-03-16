"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LogSnapshot } from "../../../components/log-snapshot";
import { PaginationControls } from "../../../components/pagination-controls";
import { apiJson, API_BASE_URL } from "../../../lib/api-client";

interface ContainerDetail {
  id: string;
  name: string;
  last_logs: string[];
}

type LogSourceFilter = "all" | "snapshot" | "live";

interface LogEntry {
  id: string;
  source: Exclude<LogSourceFilter, "all">;
  text: string;
}

export default function ContainerLogsPage({
  params,
}: {
  params: { id: string };
}) {
  const containerId = params.id;
  const [detail, setDetail] = useState<ContainerDetail | null>(null);
  const [streamLogs, setStreamLogs] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<LogSourceFilter>("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setStreamLogs([]);
    const loadDetail = async () => {
      try {
        const data = await apiJson<ContainerDetail>(
          `/api/containers/${encodeURIComponent(containerId)}?tail=100`
        );
        if (isMounted) {
          setDetail(data);
          setError(null);
        }
      } catch (e) {
        if (isMounted)
          setError(e instanceof Error ? e.message : "Erreur de chargement");
      }
    };
    void loadDetail();
    return () => {
      isMounted = false;
    };
  }, [containerId]);

  useEffect(() => {
    const logsSource = new EventSource(
      `${API_BASE_URL || ""}/api/containers/${encodeURIComponent(containerId)}/logs?tail=100`
    );

    logsSource.addEventListener("log", (event) => {
      const message = event as MessageEvent;
      const payload = JSON.parse(message.data) as { line: string };
      setStreamLogs((previous) => [...previous.slice(-299), payload.line]);
    });

    logsSource.onerror = () => {
      logsSource.close();
    };

    return () => {
      logsSource.close();
    };
  }, [containerId]);

  useEffect(() => {
    setPage(1);
  }, [searchQuery, sourceFilter]);

  const snapshotEntries: LogEntry[] =
    detail?.last_logs.map((line, index) => ({
      id: `snapshot-${index}`,
      source: "snapshot",
      text: line,
    })) ?? [];
  const liveEntries: LogEntry[] = streamLogs.map((line, index) => ({
    id: `live-${index}`,
    source: "live",
    text: line,
  }));
  const normalizedSearch = searchQuery.trim().toLowerCase();
  const filteredEntries = [...snapshotEntries, ...liveEntries].filter(
    (entry) => {
      const matchesSource =
        sourceFilter === "all" || entry.source === sourceFilter;
      const matchesSearch =
        !normalizedSearch ||
        entry.text.toLowerCase().includes(normalizedSearch);
      return matchesSource && matchesSearch;
    }
  );
  const totalPages = Math.max(1, Math.ceil(filteredEntries.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageStart = (safePage - 1) * pageSize;
  const paginatedEntries = filteredEntries.slice(
    pageStart,
    pageStart + pageSize
  );

  useEffect(() => {
    if (page !== safePage) {
      setPage(safePage);
    }
  }, [page, safePage]);

  if (error) {
    return (
      <main className="page-shell mx-auto max-w-4xl p-4">
        <p className="text-red-400">Erreur: {error}</p>
      </main>
    );
  }

  if (!detail) {
    return <main className="page-shell p-4">Chargement...</main>;
  }

  return (
    <main className="page-shell mx-auto max-w-4xl space-y-4 p-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">Logs · {detail.name}</h1>
        <div className="top-nav">
          <Link href={`/containers/${encodeURIComponent(containerId)}`}>
            Vue generale
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/commands`}
          >
            Commandes
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/environment`}
          >
            Environnement
          </Link>
        </div>
      </div>

      <section className="panel space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="md:col-span-2">
            <span className="field-label">Recherche</span>
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Chercher dans les lignes de log…"
              className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2"
            />
          </label>
          <label>
            <span className="field-label">Source</span>
            <select
              value={sourceFilter}
              onChange={(event) =>
                setSourceFilter(event.target.value as LogSourceFilter)
              }
              className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2"
            >
              <option value="all">Snapshot + live</option>
              <option value="snapshot">Snapshot</option>
              <option value="live">Live</option>
            </select>
          </label>
          <div className="flex items-end">
            <p className="text-sm text-slate-400">
              Snapshot: {snapshotEntries.length} ligne
              {snapshotEntries.length > 1 ? "s" : ""} · Live:{" "}
              {liveEntries.length} ligne{liveEntries.length > 1 ? "s" : ""}
            </p>
          </div>
        </div>

        <PaginationControls
          total={filteredEntries.length}
          page={safePage}
          pageSize={pageSize}
          itemLabel="ligne"
          pageSizeOptions={[25, 50, 100]}
          onPageChange={setPage}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(nextPageSize);
            setPage(1);
          }}
        />
      </section>

      <section className="panel space-y-3">
        <LogSnapshot
          lines={paginatedEntries.map(
            (entry) => `[${entry.source}] ${entry.text}`
          )}
          title="Logs filtrés"
          subtitle="Snapshot initial et buffer live SSE du conteneur."
          emptyLabel="Aucune ligne de log"
          maxHeightClassName="max-h-[32rem]"
          ariaLive={sourceFilter === "live" ? "polite" : "off"}
        />

        <PaginationControls
          total={filteredEntries.length}
          page={safePage}
          pageSize={pageSize}
          itemLabel="ligne"
          pageSizeOptions={[25, 50, 100]}
          onPageChange={setPage}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(nextPageSize);
            setPage(1);
          }}
        />
      </section>
    </main>
  );
}
