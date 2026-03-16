"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiJson, ApiClientError, apiFetch } from "./lib/api-client";
import { useAuth } from "./contexts/auth-context";
import { useConfirm } from "./components/confirm-dialog";
import { useNotifications } from "./components/notifications";
import { PaginationControls } from "@/app/components/pagination-controls";

type StatusFilter = "all" | "running" | "exited";

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
  return (
    container.status !== "running" && container.last_down_reason === "exited"
  );
}

export default function DashboardPage() {
  const { isAdmin } = useAuth();
  const notify = useNotifications();
  const confirm = useConfirm();
  const [containers, setContainers] = useState<Container[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingContainerId, setDeletingContainerId] = useState<string | null>(
    null
  );
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);

  const fetchContainers = useCallback(
    async (isRefresh = false): Promise<Container[]> => {
      if (!isRefresh) setLoading(true);
      try {
        const params = statusFilter === "all" ? "" : `?status=${statusFilter}`;
        const data = await apiJson<Container[]>(`/api/containers${params}`);
        setContainers(data);
        setError(null);
        return data;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur");
        return [];
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [statusFilter]
  );

  useEffect(() => {
    fetchContainers();
  }, [fetchContainers]);

  useEffect(() => {
    setSelectedIds(new Set());
    setCurrentPage(1);
  }, [statusFilter, searchQuery]);

  const action = async (id: string, action: "start" | "stop" | "restart") => {
    try {
      await apiFetch(`/api/containers/${id}/${action}`, {
        method: "POST",
      });
      const refreshedContainers = await fetchContainers();
      if (action === "start") {
        const refreshed = refreshedContainers.find(
          (container) => container.id === id
        );
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

  const toggleSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    const visibleIds = paginatedContainers.map((container) => container.id);
    const allVisibleSelected =
      visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        visibleIds.forEach((id) => next.delete(id));
      } else {
        visibleIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const bulkStart = async () => {
    const ids = containers
      .filter((c) => selectedIds.has(c.id) && c.status !== "running")
      .map((c) => c.id);
    if (ids.length === 0) return;
    setBulkLoading(true);
    try {
      const res = await apiJson<{
        ok: boolean;
        succeeded: string[];
        failed: { id: string; reason: string }[];
      }>("/api/containers/bulk/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      await fetchContainers(true);
      setSelectedIds(new Set());
      if (res.failed.length > 0) {
        notify.error(
          `${res.succeeded.length} démarré(s), ${res.failed.length} échec(s)`
        );
      } else {
        notify.info(`${res.succeeded.length} conteneur(s) démarré(s)`);
      }
    } catch (e) {
      notify.error(e instanceof ApiClientError ? e.message : "Erreur");
    } finally {
      setBulkLoading(false);
    }
  };

  const bulkStop = async () => {
    const ids = containers
      .filter((c) => selectedIds.has(c.id) && c.status === "running")
      .map((c) => c.id);
    if (ids.length === 0) return;
    setBulkLoading(true);
    try {
      const res = await apiJson<{
        ok: boolean;
        succeeded: string[];
        failed: { id: string; reason: string }[];
      }>("/api/containers/bulk/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      await fetchContainers(true);
      setSelectedIds(new Set());
      if (res.failed.length > 0) {
        notify.error(
          `${res.succeeded.length} arrêté(s), ${res.failed.length} échec(s)`
        );
      } else {
        notify.info(`${res.succeeded.length} conteneur(s) arrêté(s)`);
      }
    } catch (e) {
      notify.error(e instanceof ApiClientError ? e.message : "Erreur");
    } finally {
      setBulkLoading(false);
    }
  };

  const bulkDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    const names = containers
      .filter((c) => selectedIds.has(c.id))
      .map((c) => c.name);
    const confirmed = await confirm({
      title: "Supprimer les conteneurs",
      message: `Supprimer ${ids.length} conteneur(s) : ${names.slice(0, 5).join(", ")}${names.length > 5 ? ` …` : ""} ?`,
      confirmLabel: "Supprimer",
      cancelLabel: "Annuler",
      tone: "danger",
      requireText: "SUPPRIMER",
      inputLabel: "Pour confirmer, tapez",
      inputPlaceholder: "SUPPRIMER",
      delaySeconds: 3,
    });
    if (!confirmed) return;
    setBulkLoading(true);
    try {
      const res = await apiJson<{
        ok: boolean;
        succeeded: string[];
        failed: { id: string; reason: string }[];
      }>("/api/containers/bulk/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids, force: false, volumes: false }),
      });
      await fetchContainers(true);
      setSelectedIds(new Set());
      if (res.failed.length > 0) {
        notify.error(
          `${res.succeeded.length} supprimé(s), ${res.failed.length} échec(s)`
        );
      } else {
        notify.info(`${res.succeeded.length} conteneur(s) supprimé(s)`);
      }
    } catch (e) {
      notify.error(e instanceof ApiClientError ? e.message : "Erreur");
    } finally {
      setBulkLoading(false);
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

  const normalizedSearch = searchQuery.trim().toLowerCase();
  const filteredContainers = containers.filter((container) => {
    if (!normalizedSearch) return true;
    return [
      container.id,
      container.name,
      container.image,
      container.status,
      container.last_down_reason ?? "",
    ]
      .join(" ")
      .toLowerCase()
      .includes(normalizedSearch);
  });
  const totalPages = Math.max(
    1,
    Math.ceil(filteredContainers.length / pageSize)
  );
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const pageStart = (safeCurrentPage - 1) * pageSize;
  const paginatedContainers = filteredContainers.slice(
    pageStart,
    pageStart + pageSize
  );
  const visibleSelectedCount = paginatedContainers.filter((container) =>
    selectedIds.has(container.id)
  ).length;
  const canBulkStart = containers.some(
    (c) => selectedIds.has(c.id) && c.status !== "running"
  );
  const canBulkStop = containers.some(
    (c) => selectedIds.has(c.id) && c.status === "running"
  );

  useEffect(() => {
    if (currentPage !== safeCurrentPage) {
      setCurrentPage(safeCurrentPage);
    }
  }, [currentPage, safeCurrentPage]);

  if (loading)
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <div className="page-header mb-6">
          <h1 className="page-title text-2xl font-bold">Conteneurs Docker</h1>
        </div>
        <div className="loading-placeholder">
          <div className="loading-placeholder__spinner" aria-hidden />
          <p className="loading-placeholder__text">
            Chargement des conteneurs…
          </p>
        </div>
      </main>
    );
  if (error)
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <div className="page-header mb-6">
          <h1 className="page-title text-2xl font-bold">Conteneurs Docker</h1>
        </div>
        <div className="error-state">
          <span className="error-state__icon" aria-hidden>
            ⚠
          </span>
          <p className="error-state__message">Erreur : {error}</p>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setLoading(true);
              void fetchContainers();
            }}
            className="btn btn-neutral mt-3 px-4 py-2"
          >
            Réessayer
          </button>
        </div>
      </main>
    );

  const onRefresh = () => {
    setRefreshing(true);
    void fetchContainers(true);
  };

  const selectedCount = selectedIds.size;

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto">
      <div className="page-header mb-6">
        <h1 className="page-title text-2xl font-bold">Conteneurs Docker</h1>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="btn btn-neutral px-3 py-1.5 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {refreshing ? "Rafraîchissement…" : "Rafraîchir"}
          </button>
          <div className="top-nav">
            <Link href="/images">Images</Link>
            <Link href="/volumes">Volumes</Link>
            <Link href="/commands">Commandes</Link>
            <Link href="/alerts">Alertes</Link>
            <Link href="/audit">Audit</Link>
            <Link href="/settings">Paramètres</Link>
          </div>
        </div>
      </div>

      <div className="containers-controls">
        <div className="list-filters-panel">
          <div className="list-filters-header">
            <div>
              <p className="list-filters-title">Filtrer les conteneurs</p>
              <p className="list-filters-subtitle">
                Recherche rapide, statut et pagination de la liste.
              </p>
            </div>
            <span className="list-summary-badge">
              {filteredContainers.length} résultat
              {filteredContainers.length > 1 ? "s" : ""}
            </span>
          </div>

          <div className="list-filters-grid">
            <label className="list-field list-field--wide">
              <span className="field-label">Recherche</span>
              <input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Nom, image, ID, statut, raison…"
                className="list-input"
              />
            </label>
            <div className="list-field list-field--summary">
              <span className="field-label">Portée</span>
              <p className="list-summary-text">
                {filteredContainers.length !== containers.length
                  ? `${filteredContainers.length} visibles sur ${containers.length}`
                  : `${containers.length} visibles`}
              </p>
            </div>
          </div>

          <PaginationControls
            total={filteredContainers.length}
            page={safeCurrentPage}
            pageSize={pageSize}
            itemLabel="conteneur"
            onPageChange={setCurrentPage}
            onPageSizeChange={(nextPageSize) => {
              setPageSize(nextPageSize);
              setCurrentPage(1);
            }}
          />
        </div>

        <div
          className="status-tabs"
          role="tablist"
          aria-label="Filtrer par statut des conteneurs"
        >
          {(
            [
              ["all", "Tous", "neutral"],
              ["running", "En cours", "running"],
              ["exited", "Arrêtés", "exited"],
            ] as const
          ).map(([value, label, kind]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={statusFilter === value}
              aria-controls="containers-list"
              id={`tab-${value}`}
              onClick={() => setStatusFilter(value)}
              className={`status-tab status-tab--${kind} ${
                statusFilter === value ? "status-tab--active" : ""
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {selectedCount > 0 && isAdmin && (
          <div
            className="bulk-actions-bar"
            role="toolbar"
            aria-label="Actions en masse"
          >
            <span className="bulk-actions-count">
              {selectedCount} sélectionné(s)
            </span>
            <button
              type="button"
              onClick={selectAll}
              className="bulk-actions-select-all"
            >
              {visibleSelectedCount === paginatedContainers.length &&
              paginatedContainers.length > 0
                ? "Désélectionner la page"
                : "Sélectionner la page"}
            </button>
            <div className="bulk-actions-buttons">
              {canBulkStart && (
                <button
                  type="button"
                  onClick={bulkStart}
                  disabled={bulkLoading}
                  className="bulk-btn bulk-btn--start"
                >
                  Démarrer
                </button>
              )}
              {canBulkStop && (
                <button
                  type="button"
                  onClick={bulkStop}
                  disabled={bulkLoading}
                  className="bulk-btn bulk-btn--stop"
                >
                  Arrêter
                </button>
              )}
              <button
                type="button"
                onClick={bulkDelete}
                disabled={bulkLoading}
                className="bulk-btn bulk-btn--delete"
              >
                Supprimer
              </button>
            </div>
          </div>
        )}
      </div>

      <ul id="containers-list" className="containers-list" role="tabpanel">
        {filteredContainers.length === 0 ? (
          <li className="empty-state">
            <span className="empty-state__icon" aria-hidden>
              📦
            </span>
            <p className="empty-state__text">
              {normalizedSearch
                ? "Aucun conteneur ne correspond à la recherche"
                : statusFilter === "all"
                  ? "Aucun conteneur"
                  : statusFilter === "running"
                    ? "Aucun conteneur en cours"
                    : "Aucun conteneur arrêté"}
            </p>
          </li>
        ) : (
          paginatedContainers.map((c) => (
            <li
              key={c.id}
              className={`container-card container-card--${
                c.status === "running" ? "running" : "exited"
              } ${selectedIds.has(c.id) ? "container-card--selected" : ""}`}
            >
              <div className="container-card__main">
                {isAdmin && (
                  <label className="container-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(c.id)}
                      onChange={() => toggleSelection(c.id)}
                      aria-label={`Sélectionner ${c.name}`}
                    />
                    <span
                      className="container-checkbox__indicator"
                      aria-hidden
                    />
                  </label>
                )}
                <div className="container-card__info">
                  <div className="container-card__header">
                    <p className="container-card__name">{c.name}</p>
                    {isOneShotContainer(c) && (
                      <span className="container-badge container-badge--oneshot">
                        one-shot
                      </span>
                    )}
                  </div>
                  <p className="container-card__link">
                    <Link href={`/containers/${encodeURIComponent(c.id)}`}>
                      Voir les détails
                    </Link>
                  </p>
                  <p className="container-card__image">{c.image}</p>
                  <div className="container-card__status-row">
                    <span
                      className={`container-status-badge container-status-badge--${
                        c.status === "running" ? "running" : "exited"
                      }`}
                    >
                      {c.status}
                    </span>
                    {c.uptime_seconds != null && (
                      <span className="container-card__uptime">
                        {formatUptime(c.uptime_seconds)}
                      </span>
                    )}
                  </div>
                  {c.status !== "running" && c.last_down_reason && (
                    <p className="container-card__reason">
                      Raison : {c.last_down_reason}
                    </p>
                  )}
                  {isOneShotContainer(c) && (
                    <p className="container-card__hint">
                      Ce conteneur exécute une tâche courte puis s&apos;arrête
                      normalement.
                    </p>
                  )}
                </div>
              </div>
              {isAdmin ? (
                <div className="container-card__actions">
                  {c.status === "running" ? (
                    <>
                      <button
                        type="button"
                        onClick={() => action(c.id, "restart")}
                        disabled={deletingContainerId === c.id}
                        className="container-btn container-btn--restart"
                      >
                        Redémarrer
                      </button>
                      <button
                        type="button"
                        onClick={() => action(c.id, "stop")}
                        disabled={deletingContainerId === c.id}
                        className="container-btn container-btn--stop"
                      >
                        Arrêter
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => action(c.id, "start")}
                      disabled={deletingContainerId === c.id}
                      className="container-btn container-btn--start"
                    >
                      Démarrer
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void deleteContainerSafely(c)}
                    disabled={deletingContainerId === c.id}
                    className="container-btn container-btn--delete"
                  >
                    {deletingContainerId === c.id
                      ? "Suppression…"
                      : "Supprimer"}
                  </button>
                </div>
              ) : (
                <div className="container-card__actions">
                  <span className="text-xs text-slate-500 italic">
                    Lecture seule
                  </span>
                </div>
              )}
            </li>
          ))
        )}
      </ul>

      <PaginationControls
        total={filteredContainers.length}
        page={safeCurrentPage}
        pageSize={pageSize}
        itemLabel="conteneur"
        onPageChange={setCurrentPage}
        onPageSizeChange={(nextPageSize) => {
          setPageSize(nextPageSize);
          setCurrentPage(1);
        }}
      />
    </main>
  );
}
