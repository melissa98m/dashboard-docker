"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, apiJson } from "../../lib/api-client";
import { useAuth } from "../../contexts/auth-context";
import { useNotifications } from "../../components/notifications";

interface CommandSpec {
  id: number;
  container_id: string;
  service_name: string;
  name: string;
  argv: string[];
}

interface ContainerOption {
  id: string;
  name: string;
}

interface DiscoveredCommand {
  id: number;
  container_id: string;
  service_name: string;
  name: string;
  argv: string[];
  source: string;
}

interface AllowlistResponse {
  spec_id: number;
}

async function fetchContainersWithRetry(
  maxRetries = 2
): Promise<ContainerOption[]> {
  let lastError: Error | null = null;
  let delayMs = 300;
  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    try {
      return await apiJson<ContainerOption[]>("/api/containers");
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Erreur");
      if (attempt === maxRetries) break;
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      delayMs *= 2;
    }
  }
  throw lastError ?? new Error("Erreur");
}

export default function CommandsCatalogPage() {
  const { isAdmin } = useAuth();
  const notify = useNotifications();
  const router = useRouter();
  const [specs, setSpecs] = useState<CommandSpec[]>([]);
  const [discoveredCommands, setDiscoveredCommands] = useState<
    DiscoveredCommand[]
  >([]);
  const [containers, setContainers] = useState<ContainerOption[]>([]);
  const [reloadingContainers, setReloadingContainers] = useState(false);
  const [scanContainerId, setScanContainerId] = useState("");
  const [forceScan, setForceScan] = useState(false);
  const [discoveredContainerFilter, setDiscoveredContainerFilter] =
    useState("");
  const [scanningContainerId, setScanningContainerId] = useState<string | null>(
    null
  );
  const [promotingDiscoveredId, setPromotingDiscoveredId] = useState<
    number | null
  >(null);
  const [containerId, setContainerId] = useState("");
  const [serviceName, setServiceName] = useState("");
  const [name, setName] = useState("");
  const [argv, setArgv] = useState("");
  const [cwd, setCwd] = useState("");
  const [commandSearch, setCommandSearch] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const discoveredUrl = discoveredContainerFilter
    ? `/api/commands/discovered?container_id=${encodeURIComponent(discoveredContainerFilter)}&limit=200`
    : "/api/commands/discovered?limit=200";

  const loadData = useCallback(
    async (isManualRefresh = false) => {
      if (isManualRefresh) setRefreshing(true);
      try {
        const [specsPayload, discoveredPayload, containersData] =
          await Promise.all([
            apiJson<CommandSpec[]>("/api/commands/specs"),
            apiJson<DiscoveredCommand[]>(discoveredUrl),
            fetchContainersWithRetry(),
          ]);
        setSpecs(Array.isArray(specsPayload) ? specsPayload : []);
        setDiscoveredCommands(
          Array.isArray(discoveredPayload) ? discoveredPayload : []
        );
        setContainers(containersData);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur");
      } finally {
        if (isManualRefresh) setRefreshing(false);
      }
    },
    [discoveredUrl]
  );

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    const timer = setInterval(() => {
      void loadData();
    }, 4000);
    return () => clearInterval(timer);
  }, [loadData]);

  useEffect(() => {
    if (scanContainerId) return;
    if (containers.length === 0) return;
    setScanContainerId(containers[0].id);
  }, [containers, scanContainerId]);

  const reloadContainers = useCallback(async () => {
    setReloadingContainers(true);
    try {
      setContainers(await fetchContainersWithRetry());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    } finally {
      setReloadingContainers(false);
    }
  }, []);

  const filteredSpecs = useMemo(() => {
    const query = commandSearch.trim().toLowerCase();
    if (!query) return specs;
    return specs.filter((spec) =>
      [spec.name, spec.service_name, spec.container_id, spec.argv.join(" ")]
        .join(" ")
        .toLowerCase()
        .includes(query)
    );
  }, [specs, commandSearch]);

  const onCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      const argvList = argv
        .split(" ")
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
      await apiFetch("/api/commands/specs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          container_id: containerId,
          service_name: serviceName,
          name,
          argv: argvList,
          cwd: cwd || null,
          env_allowlist: [],
        }),
      });
      setContainerId("");
      setServiceName("");
      setName("");
      setArgv("");
      setCwd("");
      await loadData();
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Erreur");
    }
  };

  const runSpec = async (specId: number) => {
    try {
      const payload = await apiJson<{ execution_id: number }>(
        "/api/commands/execute",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ spec_id: specId }),
        }
      );
      if (typeof payload.execution_id === "number") {
        router.push(
          `/commands/live?execution=${encodeURIComponent(String(payload.execution_id))}`
        );
      } else {
        router.push("/commands/live");
      }
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Erreur");
    }
  };

  const onScanCommands = async () => {
    if (!scanContainerId) return;
    setScanningContainerId(scanContainerId);
    try {
      await apiFetch("/api/commands/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          container_id: scanContainerId,
          force: forceScan,
        }),
      });
      await loadData();
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Erreur");
    } finally {
      setScanningContainerId(null);
    }
  };

  const onAllowlistAndRun = async (item: DiscoveredCommand) => {
    setPromotingDiscoveredId(item.id);
    try {
      const payload = await apiJson<AllowlistResponse>(
        `/api/commands/discovered/${item.id}/allowlist`,
        {
          method: "POST",
        }
      );
      await runSpec(payload.spec_id);
      await loadData();
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Erreur");
    } finally {
      setPromotingDiscoveredId(null);
    }
  };

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">
          Catalogue de commandes
        </h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void loadData(true)}
            disabled={refreshing}
            className="btn btn-neutral px-3 py-1.5 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {refreshing ? "Rafraîchissement…" : "Rafraîchir"}
          </button>
          <div className="top-nav">
            <Link href="/commands/live">Terminal live</Link>
            <Link href="/commands/history">Historique</Link>
          </div>
        </div>
      </div>

      {error && (
        <section className="panel">
          <p className="text-red-400">Erreur : {error}</p>
          <button
            type="button"
            onClick={() => void loadData(true)}
            className="btn btn-neutral mt-2 px-3 py-1.5 text-sm"
          >
            Réessayer
          </button>
        </section>
      )}

      <section className="grid gap-4 lg:grid-cols-2">
        {isAdmin && (
          <div className="panel">
            <h2 className="font-semibold mb-1">
              Ajouter une commande allowlistée
            </h2>
            <p className="text-xs muted mb-3">
              Commande manuelle sécurisée (argv).
            </p>
            <form onSubmit={onCreate} className="grid gap-2">
              <label>
                <span className="field-label">Conteneur cible</span>
                <select
                  value={containerId}
                  onChange={(e) => setContainerId(e.target.value)}
                  required
                  className="rounded bg-slate-900 px-3 py-2 border border-slate-700 w-full"
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
                    {reloadingContainers
                      ? "Chargement…"
                      : "Rafraîchir la liste"}
                  </button>
                </div>
              )}
              <label>
                <span className="field-label">Nom du service</span>
                <input
                  value={serviceName}
                  onChange={(e) => setServiceName(e.target.value)}
                  placeholder="Nom du service"
                  required
                  className="rounded bg-slate-900 px-3 py-2 border border-slate-700 w-full"
                />
              </label>
              <label>
                <span className="field-label">Nom affiche</span>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Nom affiché"
                  required
                  className="rounded bg-slate-900 px-3 py-2 border border-slate-700 w-full"
                />
              </label>
              <label>
                <span className="field-label">Commande (argv)</span>
                <input
                  value={argv}
                  onChange={(e) => setArgv(e.target.value)}
                  placeholder="argv (ex: pytest -q)"
                  required
                  className="rounded bg-slate-900 px-3 py-2 border border-slate-700 w-full"
                />
              </label>
              <label>
                <span className="field-label">
                  Répertoire de travail (optionnel)
                </span>
                <input
                  value={cwd}
                  onChange={(e) => setCwd(e.target.value)}
                  placeholder="cwd (optional)"
                  className="rounded bg-slate-900 px-3 py-2 border border-slate-700 w-full"
                />
              </label>
              <button type="submit" className="btn btn-success">
                Ajouter
              </button>
            </form>
          </div>
        )}

        {isAdmin && (
          <div className="panel">
            <h2 className="font-semibold mb-1">Découverte auto</h2>
            <p className="text-xs muted mb-3">
              Scan par conteneur puis promotion allowlist.
            </p>
            <label>
              <span className="field-label">Conteneur à scanner</span>
              <select
                value={scanContainerId}
                onChange={(e) => setScanContainerId(e.target.value)}
                disabled={scanningContainerId != null}
                className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
              >
                {containers.map((container) => (
                  <option key={container.id} value={container.id}>
                    Scanner: {container.name} ({container.id})
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void onScanCommands()}
              disabled={!scanContainerId || scanningContainerId != null}
              className="btn btn-primary mt-2 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {scanningContainerId ? "Scan…" : "Scanner les commandes"}
            </button>
            <label
              className={`field-check mt-2${scanningContainerId != null ? " is-disabled" : ""}`}
            >
              <input
                type="checkbox"
                checked={forceScan}
                disabled={scanningContainerId != null}
                onChange={(e) => setForceScan(e.target.checked)}
              />
              Scan forcé
            </label>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h2 className="font-semibold">Commandes allowlistées</h2>
          <label>
            <span className="field-label">Recherche commande</span>
            <input
              value={commandSearch}
              onChange={(e) => setCommandSearch(e.target.value)}
              placeholder="Rechercher nom / service / conteneur"
              className="rounded bg-slate-900 px-3 py-1.5 border border-slate-700 text-sm min-w-64"
            />
          </label>
        </div>
        <ul className="space-y-2">
          {filteredSpecs.map((spec) => (
            <li key={spec.id} className="entity-card">
              <p className="font-medium">{spec.name}</p>
              <p className="text-xs muted">
                {spec.service_name} · {spec.container_id}
              </p>
              <p className="text-xs mt-1">{spec.argv.join(" ")}</p>
              {isAdmin && (
                <button
                  onClick={() => void runSpec(spec.id)}
                  className="btn btn-primary mt-2 px-3 py-1"
                >
                  Exécuter
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h2 className="font-semibold mb-3">Commandes découvertes</h2>
        <div className="grid gap-2 mb-3">
          <label>
            <span className="field-label">Filtre conteneur</span>
            <select
              value={discoveredContainerFilter}
              onChange={(e) => setDiscoveredContainerFilter(e.target.value)}
              className="rounded bg-slate-900 px-3 py-2 border border-slate-700 w-full"
            >
              <option value="">Filtre: tous les conteneurs</option>
              {containers.map((container) => (
                <option key={container.id} value={container.id}>
                  {container.name} ({container.id})
                </option>
              ))}
            </select>
          </label>
        </div>
        <ul className="space-y-2">
          {discoveredCommands.map((item) => (
            <li key={item.id} className="entity-card">
              <p className="font-medium">{item.name}</p>
              <p className="text-xs muted">
                {item.service_name} · {item.container_id} · source {item.source}
              </p>
              <p className="text-xs mt-1">{item.argv.join(" ")}</p>
              {isAdmin && (
                <button
                  onClick={() => void onAllowlistAndRun(item)}
                  disabled={promotingDiscoveredId === item.id}
                  className="btn btn-success mt-2 px-3 py-1 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {promotingDiscoveredId === item.id
                    ? "Validation…"
                    : "Valider et lancer"}
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
