"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { PaginationControls } from "@/app/components/pagination-controls";
import { useConfirm } from "../components/confirm-dialog";
import { LogSnapshot, splitLogLines } from "../components/log-snapshot";
import { useNotifications } from "../components/notifications";
import { apiFetch, apiJson } from "../lib/api-client";

interface AuditLogItem {
  id: number;
  action: string;
  resource_type: string;
  resource_id: string | null;
  triggered_by: string;
  details: Record<string, unknown>;
  created_at: string;
}

interface AuditLogListResponse {
  items: AuditLogItem[];
  total: number;
  limit: number;
  offset: number;
}

interface AuditFilters {
  action: string;
  resourceType: string;
  triggeredBy: string;
  query: string;
}

const defaultFilters: AuditFilters = {
  action: "",
  resourceType: "",
  triggeredBy: "",
  query: "",
};

export default function AuditPage() {
  const notify = useNotifications();
  const confirm = useConfirm();
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [filters, setFilters] = useState<AuditFilters>(defaultFilters);
  const [appliedFilters, setAppliedFilters] =
    useState<AuditFilters>(defaultFilters);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [purgeDays, setPurgeDays] = useState("90");
  const [purgeEstimate, setPurgeEstimate] = useState<number | null>(null);

  const loadLogs = async (
    nextFilters: AuditFilters,
    nextPage: number,
    nextPageSize: number
  ) => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        include_total: "true",
        limit: String(nextPageSize),
        offset: String((nextPage - 1) * nextPageSize),
      });
      if (nextFilters.action.trim())
        params.set("action", nextFilters.action.trim());
      if (nextFilters.resourceType.trim())
        params.set("resource_type", nextFilters.resourceType.trim());
      if (nextFilters.triggeredBy.trim())
        params.set("triggered_by", nextFilters.triggeredBy.trim());
      if (nextFilters.query.trim()) params.set("q", nextFilters.query.trim());

      const data = await apiJson<AuditLogListResponse>(
        `/api/audit/logs?${params.toString()}`
      );
      setLogs(data.items);
      setTotal(data.total);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadLogs(appliedFilters, page, pageSize);
  }, [appliedFilters, page, pageSize]);

  const onFilterSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPage(1);
    setAppliedFilters({ ...filters });
  };

  const onResetFilters = () => {
    setFilters(defaultFilters);
    setAppliedFilters(defaultFilters);
    setPage(1);
  };

  const onPurge = async () => {
    const confirmed = await confirm({
      title: "Purger les logs d'audit",
      message: `Supprimer les logs d'audit plus vieux que ${purgeDays} jours ?`,
      confirmLabel: "Purger",
      cancelLabel: "Annuler",
      tone: "danger",
      requireText: "PURGER",
      inputLabel: "Pour confirmer, tapez",
      inputPlaceholder: "PURGER",
      delaySeconds: 3,
    });
    if (!confirmed) return;
    try {
      await apiFetch(`/api/audit/purge?days=${encodeURIComponent(purgeDays)}`, {
        method: "POST",
      });
      await loadLogs(appliedFilters, page, pageSize);
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Erreur");
    }
  };

  const onDryRun = async () => {
    try {
      const data = await apiJson<{ purgeable_rows: number }>(
        `/api/audit/purge-dry-run?days=${encodeURIComponent(purgeDays)}`
      );
      setPurgeEstimate(data.purgeable_rows);
    } catch (e) {
      notify.error(e instanceof Error ? e.message : "Erreur");
    }
  };

  return (
    <main className="page-shell mx-auto max-w-4xl space-y-4 p-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">Audit Log</h1>
        <div className="top-nav">
          <Link href="/settings">Parametres</Link>
          <Link href="/">Dashboard</Link>
        </div>
      </div>

      <section className="panel list-filters-panel">
        <div className="list-filters-header">
          <div>
            <p className="list-filters-title">Recherche et filtres</p>
            <p className="list-filters-subtitle">
              Combine texte libre, action, type de ressource et acteur.
            </p>
          </div>
          <span className="list-summary-badge">
            {total} entrée{total > 1 ? "s" : ""}
          </span>
        </div>

        <form onSubmit={onFilterSubmit} className="list-filters-grid">
          <label className="list-field list-field--wide">
            <span className="field-label">Recherche</span>
            <input
              value={filters.query}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  query: event.target.value,
                }))
              }
              placeholder="Action, ressource, acteur, détails…"
              className="list-input"
            />
          </label>

          <label className="list-field">
            <span className="field-label">Action</span>
            <input
              value={filters.action}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  action: event.target.value,
                }))
              }
              placeholder="ex: container_restart"
              className="list-input"
            />
          </label>

          <label className="list-field">
            <span className="field-label">Type de ressource</span>
            <input
              value={filters.resourceType}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  resourceType: event.target.value,
                }))
              }
              placeholder="ex: container"
              className="list-input"
            />
          </label>

          <label className="list-field">
            <span className="field-label">Déclenché par</span>
            <input
              value={filters.triggeredBy}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  triggeredBy: event.target.value,
                }))
              }
              placeholder="ex: admin"
              className="list-input"
            />
          </label>

          <label className="list-field">
            <span className="field-label">Purge (jours)</span>
            <input
              value={purgeDays}
              onChange={(event) => {
                setPurgeDays(event.target.value);
                setPurgeEstimate(null);
              }}
              type="number"
              min="1"
              max="3650"
              className="list-input"
            />
          </label>

          <div className="list-filter-actions">
            <button type="submit" className="btn btn-primary">
              Rechercher
            </button>
            <button
              type="button"
              onClick={onResetFilters}
              className="btn btn-neutral"
            >
              Reinitialiser
            </button>
            <button type="button" onClick={onDryRun} className="btn btn-warn">
              Estimer
            </button>
            <button type="button" onClick={onPurge} className="btn btn-danger">
              Purger
            </button>
          </div>
        </form>

        <div className="list-filters-footer">
          <p className="list-summary-text">
            Historique paginé avec compteur total renvoyé par l’API.
          </p>
          {purgeEstimate != null && (
            <p className="list-summary-badge list-summary-badge--warn">
              Dry-run: {purgeEstimate} ligne(s) seraient supprimées.
            </p>
          )}
        </div>

        <PaginationControls
          total={total}
          page={page}
          pageSize={pageSize}
          itemLabel="entrée"
          onPageChange={setPage}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(nextPageSize);
            setPage(1);
          }}
        />
      </section>

      <section className="panel space-y-3">
        {loading && <p>Chargement…</p>}
        {error && <p className="text-red-400">Erreur: {error}</p>}
        {!loading && !error && logs.length === 0 && (
          <p className="text-slate-400">Aucune entrée d’audit.</p>
        )}
        <ul className="space-y-2">
          {logs.map((log) => (
            <li
              key={log.id}
              className="entity-card rounded border border-slate-700 bg-slate-900 p-3 text-sm"
            >
              <p className="font-medium">
                {log.action} · {log.resource_type}
                {log.resource_id ? `/${log.resource_id}` : ""}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                par {log.triggered_by} ·{" "}
                {new Date(log.created_at).toLocaleString()}
              </p>
              <div className="mt-2">
                <LogSnapshot
                  title="Détails"
                  lines={splitLogLines(JSON.stringify(log.details, null, 2))}
                  emptyLabel="Aucun détail"
                  maxHeightClassName="max-h-48"
                />
              </div>
            </li>
          ))}
        </ul>

        <PaginationControls
          total={total}
          page={page}
          pageSize={pageSize}
          itemLabel="entrée"
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
