"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { LogSnapshot } from "../../components/log-snapshot";
import { apiJson, API_BASE_URL } from "../../lib/api-client";

interface Execution {
  id: number;
  command_spec_id: number;
  container_id: string;
  started_at: string;
  finished_at: string | null;
  exit_code: number | null;
  triggered_by: string;
}

type LiveChannel = "stdout" | "stderr" | "system" | "done";

interface LiveLine {
  channel: LiveChannel;
  text: string;
}

function CommandsLiveContent() {
  const searchParams = useSearchParams();
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selectedExecutionId, setSelectedExecutionId] = useState<number | null>(
    null
  );
  const [liveLines, setLiveLines] = useState<LiveLine[]>([]);
  const [liveStatus, setLiveStatus] = useState<string>("idle");
  const [streamSessionNonce, setStreamSessionNonce] = useState(0);
  const [liveRetryInMs, setLiveRetryInMs] = useState<number | null>(null);
  const [autoScrollPaused, setAutoScrollPaused] = useState(false);
  const [liveFilter, setLiveFilter] = useState<"all" | LiveChannel>("all");
  const [copyFeedback, setCopyFeedback] = useState("");
  const [error, setError] = useState<string | null>(null);
  const liveOutputRef = useRef<HTMLDivElement | null>(null);

  const preselectedExecutionId = useMemo(() => {
    const value = searchParams.get("execution");
    if (!value) return null;
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) return null;
    return Math.floor(parsed);
  }, [searchParams]);

  const loadExecutions = async () => {
    try {
      const payload = await apiJson<Execution[]>("/api/commands/executions");
      setExecutions(Array.isArray(payload) ? (payload as Execution[]) : []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    }
  };

  useEffect(() => {
    void loadExecutions();
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      void loadExecutions();
    }, 4000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (preselectedExecutionId == null) return;
    setSelectedExecutionId(preselectedExecutionId);
  }, [preselectedExecutionId]);

  useEffect(() => {
    if (copyFeedback.length === 0) return;
    const timer = setTimeout(() => setCopyFeedback(""), 1400);
    return () => clearTimeout(timer);
  }, [copyFeedback]);

  useEffect(() => {
    if (selectedExecutionId == null) return;
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let retryCountdownTimer: ReturnType<typeof setInterval> | null = null;
    let reconnectAttempts = 0;
    let stopped = false;
    const maxReconnectAttempts = 5;
    const baseReconnectDelayMs = 800;
    const maxReconnectDelayMs = 5000;
    setLiveLines([]);
    setLiveStatus("connecting");
    setLiveRetryInMs(null);

    const appendLine = (channel: LiveChannel, line: string) => {
      setLiveLines((previous) => [
        ...previous.slice(-799),
        { channel, text: line },
      ]);
    };

    const connect = async () => {
      if (stopped) return;
      let streamUrl = `${API_BASE_URL || ""}/api/commands/executions/${selectedExecutionId}/stream`;
      try {
        const payload = await apiJson<{ token: string }>(
          `/api/commands/executions/${selectedExecutionId}/stream-token`
        );
        streamUrl += `?token=${encodeURIComponent(payload.token)}`;
      } catch {
        // fallback for local permissive mode
      }

      source = new EventSource(streamUrl);
      source.addEventListener("open", () => {
        setLiveStatus("connected");
        setLiveRetryInMs(null);
      });
      source.addEventListener("stdout", (event) => {
        const message = event as MessageEvent;
        const payload = JSON.parse(message.data) as { line: string };
        appendLine("stdout", payload.line);
        setLiveStatus("streaming");
        setLiveRetryInMs(null);
        reconnectAttempts = 0;
      });
      source.addEventListener("stderr", (event) => {
        const message = event as MessageEvent;
        const payload = JSON.parse(message.data) as { line: string };
        appendLine("stderr", payload.line);
        setLiveStatus("streaming");
        setLiveRetryInMs(null);
        reconnectAttempts = 0;
      });
      source.addEventListener("done", (event) => {
        const message = event as MessageEvent;
        const payload = JSON.parse(message.data) as { exit_code: number };
        appendLine("done", `exit_code=${payload.exit_code}`);
        setLiveStatus("done");
        setLiveRetryInMs(null);
        stopped = true;
        source?.close();
      });
      source.addEventListener("error", () => {
        if (stopped) return;
        reconnectAttempts += 1;
        if (reconnectAttempts > maxReconnectAttempts) {
          setLiveStatus("error");
          appendLine("system", "stream disconnected (max retries reached)");
          stopped = true;
          source?.close();
          return;
        }
        setLiveStatus("reconnecting");
        const reconnectDelayMs = Math.min(
          baseReconnectDelayMs * 2 ** (reconnectAttempts - 1),
          maxReconnectDelayMs
        );
        setLiveRetryInMs(reconnectDelayMs);
        appendLine(
          "system",
          `stream disconnected, retry ${reconnectAttempts}/${maxReconnectAttempts} in ${reconnectDelayMs}ms`
        );
        source?.close();
        if (retryCountdownTimer) clearInterval(retryCountdownTimer);
        retryCountdownTimer = setInterval(() => {
          setLiveRetryInMs((previous) => {
            if (previous == null) return previous;
            if (previous <= 250) return 0;
            return previous - 250;
          });
        }, 250);
        reconnectTimer = setTimeout(() => {
          if (retryCountdownTimer) {
            clearInterval(retryCountdownTimer);
            retryCountdownTimer = null;
          }
          setLiveRetryInMs(null);
          void connect();
        }, reconnectDelayMs);
      });
    };

    void connect();
    return () => {
      stopped = true;
      source?.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (retryCountdownTimer) clearInterval(retryCountdownTimer);
      setLiveRetryInMs(null);
    };
  }, [selectedExecutionId, streamSessionNonce]);

  useEffect(() => {
    const node = liveOutputRef.current;
    if (!node) return;
    if (autoScrollPaused) return;
    node.scrollTop = node.scrollHeight;
  }, [liveLines, autoScrollPaused]);

  const sortedExecutions = useMemo(() => {
    return [...executions].sort(
      (a, b) =>
        new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
    );
  }, [executions]);

  const filteredLiveLines = useMemo(() => {
    if (liveFilter === "all") return liveLines;
    return liveLines.filter((line) => line.channel === liveFilter);
  }, [liveFilter, liveLines]);

  const renderedLiveLines = useMemo(() => {
    return filteredLiveLines.map((line) => `[${line.channel}] ${line.text}`);
  }, [filteredLiveLines]);

  const scrollLiveToBottom = () => {
    const node = liveOutputRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  };

  const clearLiveOutput = () => {
    setLiveLines([]);
  };

  const copyLiveOutput = async () => {
    const text = renderedLiveLines.join("\n");
    if (!text) {
      setCopyFeedback("Aucune ligne a copier");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setCopyFeedback("Copie");
    } catch {
      setCopyFeedback("Copie impossible");
    }
  };

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">Terminal live</h1>
        <div className="top-nav">
          <Link href="/commands/catalog">Catalogue</Link>
          <Link href="/commands/history">Historique</Link>
        </div>
      </div>

      {error && (
        <section className="panel">
          <p className="text-red-400">Erreur: {error}</p>
        </section>
      )}

      <section className="panel">
        <h2 className="font-semibold mb-2">Executions recentes</h2>
        <ul className="space-y-2">
          {sortedExecutions.map((exec) => (
            <li key={exec.id} className="entity-card text-sm">
              <p className="flex flex-wrap items-center gap-2">
                <span>spec #{exec.command_spec_id}</span>
                {exec.exit_code == null ? (
                  <span className="text-amber-300">en cours</span>
                ) : exec.exit_code === 0 ? (
                  <span className="text-emerald-300">terminee (0)</span>
                ) : (
                  <span className="text-red-300">echec ({exec.exit_code})</span>
                )}
              </p>
              <p className="text-xs text-slate-400">
                {new Date(exec.started_at).toLocaleString()} ·{" "}
                {exec.container_id} · par {exec.triggered_by}
              </p>
              <button
                type="button"
                onClick={() => setSelectedExecutionId(exec.id)}
                className="btn btn-neutral mt-2 px-3 py-1 text-xs"
              >
                Suivre en live
              </button>
            </li>
          ))}
          {sortedExecutions.length === 0 && (
            <li className="text-xs muted">Aucune execution.</li>
          )}
        </ul>
      </section>

      <section className="panel">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
          <h2 className="font-semibold">Sortie live</h2>
          <p className="text-xs text-slate-400">
            Execution: {selectedExecutionId ?? "aucune"} · etat: {liveStatus}
          </p>
        </div>
        {selectedExecutionId == null && (
          <p className="text-xs text-slate-400 mb-2">
            Selectionne une execution depuis la liste pour ouvrir le flux.
          </p>
        )}
        {liveStatus === "reconnecting" && liveRetryInMs != null && (
          <p className="text-xs text-amber-300 mb-2">
            Reconnexion automatique dans {(liveRetryInMs / 1000).toFixed(1)}s
          </p>
        )}
        {selectedExecutionId != null && liveStatus === "error" && (
          <button
            onClick={() => setStreamSessionNonce((previous) => previous + 1)}
            className="btn btn-primary mb-2 px-3 py-1 text-xs"
          >
            Reconnecter
          </button>
        )}
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <label>
            <span className="field-label">Filtre flux</span>
            <select
              value={liveFilter}
              onChange={(e) =>
                setLiveFilter(e.target.value as "all" | LiveChannel)
              }
              disabled={selectedExecutionId == null}
              className="rounded bg-slate-900 px-2 py-1 border border-slate-700 text-xs"
            >
              <option value="all">tout</option>
              <option value="stdout">stdout</option>
              <option value="stderr">stderr</option>
              <option value="system">system</option>
              <option value="done">termine</option>
            </select>
          </label>
          <label
            className={`field-check${selectedExecutionId == null ? " is-disabled" : ""}`}
          >
            <input
              type="checkbox"
              checked={autoScrollPaused}
              disabled={selectedExecutionId == null}
              onChange={(e) => setAutoScrollPaused(e.target.checked)}
            />
            Pause auto-scroll
          </label>
          <button
            type="button"
            onClick={scrollLiveToBottom}
            className="btn btn-neutral px-3 py-1 text-xs"
          >
            Aller en bas
          </button>
          <button
            type="button"
            onClick={clearLiveOutput}
            className="btn btn-neutral px-3 py-1 text-xs"
          >
            Nettoyer
          </button>
          <button
            type="button"
            onClick={() => void copyLiveOutput()}
            className="btn btn-neutral px-3 py-1 text-xs"
          >
            Copier
          </button>
          {copyFeedback && (
            <span className="text-xs text-slate-400">{copyFeedback}</span>
          )}
        </div>
        <LogSnapshot
          lines={renderedLiveLines}
          title="Flux live"
          subtitle="stdout, stderr et événements système de l'exécution sélectionnée."
          emptyLabel="Aucun flux en temps reel pour le moment."
          maxHeightClassName="max-h-64"
          viewportRef={liveOutputRef}
          ariaLive="polite"
        />
      </section>
    </main>
  );
}

export default function CommandsLivePage() {
  return (
    <Suspense
      fallback={
        <main className="page-shell p-4 max-w-4xl mx-auto">Chargement...</main>
      }
    >
      <CommandsLiveContent />
    </Suspense>
  );
}
