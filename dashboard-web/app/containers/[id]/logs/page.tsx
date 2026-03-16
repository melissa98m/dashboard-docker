"use client";

import Link from "next/link";
import { useMemo, useEffect, useState } from "react";
import { LogSnapshot } from "../../../components/log-snapshot";
import { apiJson, API_BASE_URL } from "../../../lib/api-client";

interface ContainerDetail {
  id: string;
  name: string;
  last_logs: string[];
}

export default function ContainerLogsPage({
  params,
}: {
  params: { id: string };
}) {
  const containerId = useMemo(() => params.id, [params.id]);
  const [detail, setDetail] = useState<ContainerDetail | null>(null);
  const [streamLogs, setStreamLogs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const loadDetail = async () => {
      try {
        const data = await apiJson<ContainerDetail>(
          `/api/containers/${encodeURIComponent(containerId)}?tail=100`
        );
        if (isMounted) setDetail(data);
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

  if (error) {
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <p className="text-red-400">Erreur: {error}</p>
      </main>
    );
  }

  if (!detail) {
    return <main className="page-shell p-4">Chargement...</main>;
  }

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
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

      <section className="panel">
        <LogSnapshot
          lines={detail.last_logs}
          title="Derniers logs (snapshot)"
          subtitle="Capture récente exposée par l'API du conteneur."
          emptyLabel="Aucun log"
          maxHeightClassName="max-h-64"
        />
      </section>

      <section className="panel">
        <LogSnapshot
          lines={streamLogs}
          title="Logs live (SSE)"
          subtitle="Flux temps réel du conteneur."
          emptyLabel="En attente de logs..."
          maxHeightClassName="max-h-64"
          ariaLive="polite"
        />
      </section>
    </main>
  );
}
