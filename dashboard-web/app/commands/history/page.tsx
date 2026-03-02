"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiJson } from "../../lib/api-client";

interface Execution {
  id: number;
  command_spec_id: number;
  container_id: string;
  started_at: string;
  finished_at: string | null;
  exit_code: number | null;
  triggered_by: string;
}

export default function CommandsHistoryPage() {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadExecutions = useCallback(async () => {
    try {
      const payload = await apiJson<Execution[]>("/api/commands/executions");
      setExecutions(Array.isArray(payload) ? (payload as Execution[]) : []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    }
  }, []);

  useEffect(() => {
    void loadExecutions();
  }, [loadExecutions]);

  useEffect(() => {
    const timer = setInterval(() => {
      void loadExecutions();
    }, 4000);
    return () => clearInterval(timer);
  }, [loadExecutions]);

  const sortedExecutions = useMemo(() => {
    return [...executions].sort(
      (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
    );
  }, [executions]);

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">Historique commandes</h1>
        <div className="top-nav">
          <Link href="/commands/catalog">Catalogue</Link>
          <Link href="/commands/live">Terminal live</Link>
        </div>
      </div>

      {error && (
        <section className="panel bg-slate-800 rounded-lg p-4">
          <p className="text-red-400">Erreur: {error}</p>
        </section>
      )}

      <section className="panel bg-slate-800 rounded-lg p-4">
        <h2 className="font-semibold mb-3">Exécutions</h2>
        <ul className="space-y-2">
          {sortedExecutions.map((exec) => (
            <li key={exec.id} className="entity-card bg-slate-900 rounded border border-slate-700 p-3 text-sm">
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
                {new Date(exec.started_at).toLocaleString()} · {exec.container_id} · par {exec.triggered_by}
              </p>
              <Link
                href={`/commands/live?execution=${encodeURIComponent(String(exec.id))}`}
                className="inline-block mt-2 text-xs text-sky-400 hover:text-sky-300"
              >
                Ouvrir dans terminal live
              </Link>
            </li>
          ))}
          {sortedExecutions.length === 0 && <li className="text-xs text-slate-400">Aucune exécution.</li>}
        </ul>
      </section>
    </main>
  );
}
