"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, apiJson, API_BASE_URL } from "../../../lib/api-client";
import { useAuth } from "../../../contexts/auth-context";

interface CommandSpec {
  id: number;
  container_id: string;
  service_name: string;
  name: string;
  argv: string[];
}

interface DiscoveredCommand {
  id: number;
  container_id: string;
  service_name: string;
  name: string;
  argv: string[];
  source: string;
}

interface Execution {
  id: number;
  command_spec_id: number;
  container_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  exit_code: number | null;
  duration_ms: number | null;
  triggered_by: string;
}

interface ExecutionDetail extends Execution {
  stdout_tail: string;
  stderr_tail: string;
}

type LiveChannel = "stdout" | "stderr" | "done" | "system";

interface LiveLine {
  channel: LiveChannel;
  text: string;
}

interface AllowlistResponse {
  spec_id: number;
}

interface DiscoverResponse {
  discovered_count: number;
  cached: boolean;
  cache_age_seconds: number | null;
}

export function ContainerCommandsPanel({
  containerId,
}: {
  containerId: string;
}) {
  const { isAdmin } = useAuth();
  const [specs, setSpecs] = useState<CommandSpec[]>([]);
  const [discovered, setDiscovered] = useState<DiscoveredCommand[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selectedExecutionId, setSelectedExecutionId] = useState<number | null>(
    null
  );
  const [selectedDetail, setSelectedDetail] = useState<ExecutionDetail | null>(
    null
  );
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [liveLines, setLiveLines] = useState<LiveLine[]>([]);
  const [liveStatus, setLiveStatus] = useState("idle");
  const [forceScan, setForceScan] = useState(false);
  const [scanStatus, setScanStatus] = useState<string | null>(null);
  const [isScanning, setIsScanning] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [specsPayload, discoveredPayload, executionsPayload] =
        await Promise.all([
          apiJson<CommandSpec[]>(
            `/api/containers/${encodeURIComponent(containerId)}/commands/specs`
          ),
          apiJson<DiscoveredCommand[]>(
            `/api/containers/${encodeURIComponent(containerId)}/commands/discovered?limit=200`
          ),
          apiJson<Execution[]>(
            `/api/containers/${encodeURIComponent(containerId)}/commands/executions?limit=200`
          ),
        ]);
      setSpecs(Array.isArray(specsPayload) ? specsPayload : []);
      setDiscovered(Array.isArray(discoveredPayload) ? discoveredPayload : []);
      setExecutions(Array.isArray(executionsPayload) ? executionsPayload : []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    }
  }, [containerId]);

  useEffect(() => {
    void loadData();
    const timer = setInterval(() => {
      void loadData();
    }, 4000);
    return () => clearInterval(timer);
  }, [loadData]);

  useEffect(() => {
    if (selectedExecutionId == null) {
      setSelectedDetail(null);
      return;
    }
    let cancelled = false;
    const loadDetail = async () => {
      try {
        const payload = await apiJson<ExecutionDetail>(
          `/api/commands/executions/${encodeURIComponent(String(selectedExecutionId))}`
        );
        if (!cancelled) setSelectedDetail(payload);
      } catch {
        if (!cancelled) setSelectedDetail(null);
      }
    };
    void loadDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedExecutionId]);

  useEffect(() => {
    if (selectedExecutionId == null) return;
    let source: EventSource | null = null;
    let stopped = false;
    setLiveLines([]);
    setLiveStatus("connecting");

    const connect = async () => {
      let streamUrl = `${API_BASE_URL || ""}/api/commands/executions/${selectedExecutionId}/stream`;
      try {
        const payload = await apiJson<{ token: string }>(
          `/api/commands/executions/${selectedExecutionId}/stream-token`
        );
        streamUrl += `?token=${encodeURIComponent(payload.token)}`;
      } catch {
        // fallback when token endpoint is unavailable
      }

      source = new EventSource(streamUrl);
      source.addEventListener("stdout", (event) => {
        const message = event as MessageEvent;
        const payload = JSON.parse(message.data) as { line: string };
        setLiveLines((previous) => [
          ...previous.slice(-299),
          { channel: "stdout", text: payload.line },
        ]);
        setLiveStatus("streaming");
      });
      source.addEventListener("stderr", (event) => {
        const message = event as MessageEvent;
        const payload = JSON.parse(message.data) as { line: string };
        setLiveLines((previous) => [
          ...previous.slice(-299),
          { channel: "stderr", text: payload.line },
        ]);
        setLiveStatus("streaming");
      });
      source.addEventListener("done", (event) => {
        const message = event as MessageEvent;
        const payload = JSON.parse(message.data) as { exit_code: number };
        setLiveLines((previous) => [
          ...previous.slice(-299),
          { channel: "done", text: `exit_code=${payload.exit_code}` },
        ]);
        setLiveStatus("done");
        stopped = true;
        source?.close();
      });
      source.addEventListener("error", () => {
        if (stopped) return;
        setLiveLines((previous) => [
          ...previous.slice(-299),
          { channel: "system", text: "Stream interrompu" },
        ]);
        setLiveStatus("error");
      });
    };

    void connect();
    return () => {
      stopped = true;
      source?.close();
    };
  }, [selectedExecutionId]);

  const filteredSpecs = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return specs;
    return specs.filter((spec) =>
      [spec.name, spec.service_name, spec.argv.join(" ")]
        .join(" ")
        .toLowerCase()
        .includes(query)
    );
  }, [search, specs]);

  const sortedExecutions = useMemo(() => {
    return [...executions].sort(
      (a, b) =>
        new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
    );
  }, [executions]);

  const runSpec = async (specId: number) => {
    try {
      const payload = await apiJson<{ execution_id: number }>(
        "/api/commands/execute",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ spec_id: specId, container_id: containerId }),
        }
      );
      setSelectedExecutionId(payload.execution_id);
      await loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    }
  };

  const allowlistAndRun = async (item: DiscoveredCommand) => {
    try {
      const payload = await apiJson<AllowlistResponse>(
        `/api/commands/discovered/${item.id}/allowlist`,
        {
          method: "POST",
        }
      );
      await runSpec(payload.spec_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    }
  };

  const scanCommands = async () => {
    setIsScanning(true);
    setScanStatus(null);
    try {
      const payload = await apiJson<DiscoverResponse>(
        "/api/commands/discover",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ container_id: containerId, force: forceScan }),
        }
      );
      if (payload.cached) {
        setScanStatus(
          `Cache actif (${payload.cache_age_seconds ?? 0}s). Active "Scan forcé" pour rescanner.`
        );
      } else {
        setScanStatus(`${payload.discovered_count} commande(s) détectée(s).`);
      }
      await loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    } finally {
      setIsScanning(false);
    }
  };

  return (
    <section className="panel bg-slate-800 rounded-lg p-4 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Commandes du conteneur</h2>
        <label>
          <span className="field-label">Recherche commande</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Rechercher une commande"
            className="rounded bg-slate-900 px-3 py-1.5 border border-slate-700 text-sm min-w-60"
          />
        </label>
      </div>
      {error && <p className="text-xs text-red-400">Erreur : {error}</p>}

      <div>
        <h3 className="text-sm font-medium mb-2">Commandes allowlistées</h3>
        <ul className="space-y-2">
          {filteredSpecs.map((spec) => (
            <li
              key={spec.id}
              className="entity-card bg-slate-900 rounded border border-slate-700 p-3"
            >
              <p className="font-medium">{spec.name}</p>
              <p className="text-xs text-slate-400">{spec.service_name}</p>
              <p className="text-xs mt-1">{spec.argv.join(" ")}</p>
              {isAdmin && (
                <button
                  type="button"
                  onClick={() => void runSpec(spec.id)}
                  className="btn btn-primary mt-2 px-3 py-1 bg-sky-600 hover:bg-sky-500 rounded text-xs"
                >
                  Exécuter
                </button>
              )}
            </li>
          ))}
          {filteredSpecs.length === 0 && (
            <li className="text-xs text-slate-400">
              Aucune commande allowlistée.
            </li>
          )}
        </ul>
      </div>

      <div>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
          <h3 className="text-sm font-medium">Commandes découvertes</h3>
          {isAdmin && (
            <div className="flex items-center gap-3">
              <label
                className={`field-check${isScanning ? " is-disabled" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={forceScan}
                  disabled={isScanning}
                  onChange={(event) => setForceScan(event.target.checked)}
                />
                Scan forcé
              </label>
              <button
                type="button"
                onClick={() => void scanCommands()}
                disabled={isScanning}
                className="btn btn-primary px-3 py-1 bg-sky-600 hover:bg-sky-500 rounded text-xs disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isScanning ? "Scan…" : "Scanner"}
              </button>
            </div>
          )}
        </div>
        {scanStatus && (
          <p className="text-xs text-slate-300 mb-2">{scanStatus}</p>
        )}
        <ul className="space-y-2">
          {discovered.map((item) => (
            <li
              key={item.id}
              className="entity-card bg-slate-900 rounded border border-slate-700 p-3"
            >
              <p className="font-medium">{item.name}</p>
              <p className="text-xs text-slate-400">
                {item.service_name} · source {item.source}
              </p>
              <p className="text-xs mt-1">{item.argv.join(" ")}</p>
              {isAdmin && (
                <button
                  type="button"
                  onClick={() => void allowlistAndRun(item)}
                  className="btn btn-success mt-2 px-3 py-1 bg-emerald-600 hover:bg-emerald-500 rounded text-xs"
                >
                  Valider et lancer
                </button>
              )}
            </li>
          ))}
          {discovered.length === 0 && (
            <li className="text-xs text-slate-400">
              Aucune commande découverte.
            </li>
          )}
        </ul>
      </div>

      <div>
        <h3 className="text-sm font-medium mb-2">Historique & logs</h3>
        <ul className="space-y-2 mb-3">
          {sortedExecutions.map((execution) => (
            <li
              key={execution.id}
              className="entity-card bg-slate-900 rounded border border-slate-700 p-3 text-xs"
            >
              <p className="text-slate-200">
                #{execution.id} · spec #{execution.command_spec_id} ·{" "}
                {execution.status}
              </p>
              <p className="text-slate-400">
                {new Date(execution.started_at).toLocaleString()} · par{" "}
                {execution.triggered_by}
              </p>
              <button
                type="button"
                onClick={() => setSelectedExecutionId(execution.id)}
                className="btn btn-neutral mt-2 px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-xs"
              >
                Voir logs
              </button>
            </li>
          ))}
          {sortedExecutions.length === 0 && (
            <li className="text-xs text-slate-400">Aucune exécution.</li>
          )}
        </ul>

        <p className="text-xs text-slate-400 mb-2">
          Exécution active : {selectedExecutionId ?? "aucune"} · état stream :{" "}
          {liveStatus}
        </p>
        <pre className="code-panel text-xs whitespace-pre-wrap text-slate-300 max-h-48 overflow-auto mb-2">
          {liveLines
            .map((line) => `[${line.channel}] ${line.text}`)
            .join("\n") || "Aucun flux live"}
        </pre>
        <pre className="code-panel text-xs whitespace-pre-wrap text-slate-300 max-h-48 overflow-auto">
          {selectedDetail
            ? `${selectedDetail.stdout_tail}\n${selectedDetail.stderr_tail}`.trim() ||
              "Logs vides"
            : "Sélectionne une exécution pour afficher le snapshot stdout/stderr"}
        </pre>
      </div>
    </section>
  );
}
