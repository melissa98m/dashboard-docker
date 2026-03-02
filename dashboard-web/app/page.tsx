"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiJson, ApiClientError, apiFetch } from "./lib/api-client";
import { useConfirm } from "./components/confirm-dialog";
import { useNotifications } from "./components/notifications";

interface Container {
  id: string;
  name: string;
  image: string;
  status: string;
  uptime_seconds: number | null;
  finished_at: string | null;
  last_down_reason: string | null;
}

function formatUptime(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

function isOneShotContainer(container: Container): boolean {
  return container.status !== "running" && container.last_down_reason === "exited";
}

export default function DashboardPage() {
  const notify = useNotifications();
  const confirm = useConfirm();
  const [containers, setContainers] = useState<Container[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingContainerId, setDeletingContainerId] = useState<string | null>(null);

  const fetchContainers = async (): Promise<Container[]> => {
    try {
      const data = await apiJson<Container[]>("/api/containers");
      setContainers(data);
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
      return [];
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchContainers();
  }, []);

  const action = async (id: string, action: "start" | "stop" | "restart") => {
    try {
      await apiFetch(`/api/containers/${id}/${action}`, {
        method: "POST",
      });
      const refreshedContainers = await fetchContainers();
      if (action === "start") {
        const refreshed = refreshedContainers.find((container) => container.id === id);
        if (refreshed && refreshed.status !== "running") {
          const reason = refreshed.last_down_reason
            ? `Raison: ${refreshed.last_down_reason}`
            : "Le process principal s'est terminé juste après le démarrage.";
          notify.info(
            `Le conteneur "${refreshed.name}" a bien démarré puis s'est arrêté immédiatement. ${reason}`
          );
        }
      }
    } catch (e) {
      if (e instanceof ApiClientError) {
        notify.error(e.message);
      } else {
        notify.error(e instanceof Error ? e.message : "Erreur");
      }
    }
  };

  const deleteContainerSafely = async (container: Container) => {
    const confirmed = await confirm({
      title: "Supprimer le conteneur",
      message: `Supprimer ${container.name} ? Cette action retire le conteneur sans supprimer les volumes.`,
      confirmLabel: "Supprimer",
      cancelLabel: "Annuler",
      tone: "danger",
      requireText: "SUPPRIMER",
      inputLabel: "Pour confirmer, tapez",
      inputPlaceholder: "SUPPRIMER",
      delaySeconds: 3,
    });
    if (!confirmed) return;
    setDeletingContainerId(container.id);
    try {
      if (container.status === "running") {
        await apiFetch(`/api/containers/${container.id}/stop`, {
          method: "POST",
        });
      }
      await apiFetch(
        `/api/containers/${container.id}?force=false&volumes=false`,
        {
          method: "DELETE",
        }
      );
      await fetchContainers();
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Erreur");
    } finally {
      setDeletingContainerId(null);
    }
  };

  if (loading) return <main className="page-shell p-4">Chargement…</main>;
  if (error)
    return (
      <main className="page-shell p-4">
        <p className="text-red-400">Erreur: {error}</p>
      </main>
    );

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto">
      <div className="page-header mb-6">
        <h1 className="page-title text-2xl font-bold">Conteneurs Docker</h1>
        <div className="top-nav">
          <Link href="/commands">Commandes</Link>
          <Link href="/alerts">Alertes</Link>
          <Link href="/audit">Audit</Link>
          <Link href="/settings">Parametres</Link>
        </div>
      </div>
      <ul className="space-y-3">
        {containers.map((c) => (
          <li key={c.id} className="panel bg-slate-800 rounded-lg p-4 flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 min-w-0">
                <p className="font-medium truncate">{c.name}</p>
                {isOneShotContainer(c) && (
                  <span className="text-[10px] uppercase tracking-wide rounded bg-slate-700 text-slate-200 px-2 py-0.5">
                    one-shot
                  </span>
                )}
              </div>
              <p className="text-xs mt-1">
                <Link
                  href={`/containers/${encodeURIComponent(c.id)}`}
                  className="text-sky-400 hover:text-sky-300"
                >
                  Voir les détails
                </Link>
              </p>
              <p className="text-sm text-slate-400 truncate">{c.image}</p>
              <p className="text-sm mt-1">
                <span
                  className={
                    c.status === "running"
                      ? "text-emerald-400"
                      : "text-amber-400"
                  }
                >
                  {c.status}
                </span>
                {c.uptime_seconds != null && (
                  <span className="text-slate-500 ml-2">
                    • {formatUptime(c.uptime_seconds)}
                  </span>
                )}
              </p>
              {c.status !== "running" && c.last_down_reason && (
                <p className="text-xs text-amber-300 mt-1 break-words">
                  Raison down: {c.last_down_reason}
                </p>
              )}
              {isOneShotContainer(c) && (
                <p className="text-xs text-slate-400 mt-1">
                  Ce conteneur exécute une tâche courte puis s&apos;arrête normalement.
                </p>
              )}
            </div>
            <div className="btn-row flex gap-2">
              {c.status === "running" ? (
                <>
                  <button
                    onClick={() => action(c.id, "restart")}
                    disabled={deletingContainerId === c.id}
                    className="btn btn-warn px-4 py-2 bg-amber-600 hover:bg-amber-500 rounded-lg text-sm font-medium"
                  >
                    Redemarrer
                  </button>
                  <button
                    onClick={() => action(c.id, "stop")}
                    disabled={deletingContainerId === c.id}
                    className="btn btn-danger px-4 py-2 bg-red-600 hover:bg-red-500 rounded-lg text-sm font-medium"
                  >
                    Arreter
                  </button>
                </>
              ) : (
                <button
                  onClick={() => action(c.id, "start")}
                  disabled={deletingContainerId === c.id}
                  className="btn btn-success px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-sm font-medium"
                >
                  Demarrer
                </button>
              )}
              <button
                onClick={() => void deleteContainerSafely(c)}
                disabled={deletingContainerId === c.id}
                className="btn btn-danger px-4 py-2 bg-red-700 hover:bg-red-600 rounded-lg text-sm font-medium disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {deletingContainerId === c.id ? "Suppression..." : "Supprimer"}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
