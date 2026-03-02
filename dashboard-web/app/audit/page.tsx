"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, apiJson } from "../lib/api-client";
import { useConfirm } from "../components/confirm-dialog";
import { useNotifications } from "../components/notifications";

interface AuditLogItem {
  id: number;
  action: string;
  resource_type: string;
  resource_id: string | null;
  triggered_by: string;
  details: Record<string, unknown>;
  created_at: string;
}

export default function AuditPage() {
  const notify = useNotifications();
  const confirm = useConfirm();
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [actionFilter, setActionFilter] = useState("");
  const [limit, setLimit] = useState("100");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [purgeDays, setPurgeDays] = useState("90");
  const [purgeEstimate, setPurgeEstimate] = useState<number | null>(null);

  const loadLogs = async (action?: string) => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.set("limit", limit);
      if (action && action.trim().length > 0) {
        params.set("action", action.trim());
      }
      const data = await apiJson<AuditLogItem[]>(`/api/audit/logs?${params.toString()}`);
      setLogs(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onFilterSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await loadLogs(actionFilter);
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
      await apiFetch(
        `/api/audit/purge?days=${encodeURIComponent(purgeDays)}`,
        { method: "POST" }
      );
      await loadLogs(actionFilter);
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
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">Audit Log</h1>
        <div className="top-nav">
          <Link href="/settings">Parametres</Link>
          <Link href="/">Dashboard</Link>
        </div>
      </div>

      <section className="panel">
        <form onSubmit={onFilterSubmit} className="flex flex-wrap gap-2 items-end">
          <div className="flex-1 min-w-[220px]">
            <label className="block text-xs text-slate-400 mb-1">Action</label>
            <input
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              placeholder="ex: container_restart"
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            />
          </div>
          <div className="w-[140px]">
            <label className="block text-xs text-slate-400 mb-1">Limit</label>
            <input
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              type="number"
              min="1"
              max="500"
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            />
          </div>
          <button type="submit" className="btn btn-primary px-4 py-2 bg-sky-600 hover:bg-sky-500 rounded-lg text-sm font-medium">
            Filtrer
          </button>
          <button
            type="button"
            onClick={() => {
              setActionFilter("");
              loadLogs("");
            }}
            className="btn btn-neutral px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium"
          >
            Reinitialiser
          </button>
          <div className="w-[150px]">
            <label className="block text-xs text-slate-400 mb-1">Purge (days)</label>
            <input
              value={purgeDays}
              onChange={(e) => setPurgeDays(e.target.value)}
              type="number"
              min="1"
              max="3650"
              className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
            />
          </div>
          <button
            type="button"
            onClick={onDryRun}
            className="btn btn-warn px-4 py-2 bg-amber-700 hover:bg-amber-600 rounded-lg text-sm font-medium"
          >
            Estimer
          </button>
          <button
            type="button"
            onClick={onPurge}
            className="btn btn-danger px-4 py-2 bg-red-700 hover:bg-red-600 rounded-lg text-sm font-medium"
          >
            Purger
          </button>
          {purgeEstimate != null && (
            <p className="text-xs text-slate-300 w-full">
              Dry-run: {purgeEstimate} ligne(s) seraient supprimées.
            </p>
          )}
        </form>
      </section>

      <section className="panel">
        {loading && <p>Chargement…</p>}
        {error && <p className="text-red-400">Erreur: {error}</p>}
        {!loading && !error && logs.length === 0 && (
          <p className="text-slate-400">Aucune entrée d’audit.</p>
        )}
        <ul className="space-y-2">
          {logs.map((log) => (
            <li key={log.id} className="entity-card bg-slate-900 border border-slate-700 rounded p-3 text-sm">
              <p className="font-medium">
                {log.action} · {log.resource_type}
                {log.resource_id ? `/${log.resource_id}` : ""}
              </p>
              <p className="text-slate-400 text-xs mt-1">
                par {log.triggered_by} · {new Date(log.created_at).toLocaleString()}
              </p>
              <pre className="code-panel text-xs text-slate-300 mt-2 whitespace-pre-wrap">
                {JSON.stringify(log.details, null, 2)}
              </pre>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
