"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { apiJson } from "../../../lib/api-client";

interface WorkflowJob {
  workflow: string;
  workflow_file: string;
  job: string;
}

export function ContainerWorkflowsPanel({
  containerId,
}: {
  containerId: string;
}) {
  const [jobs, setJobs] = useState<WorkflowJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = `/api/workflows?container_id=${encodeURIComponent(containerId)}`;
      const data = await apiJson<unknown>(url);
      const list = Array.isArray(data) ? data : [];
      setJobs(
        list.filter(
          (j): j is WorkflowJob =>
            j != null &&
            typeof j === "object" &&
            typeof (j as WorkflowJob).job === "string" &&
            typeof (j as WorkflowJob).workflow_file === "string"
        )
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, [containerId]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  if (loading) {
    return (
      <section className="panel bg-slate-800 rounded-lg p-4">
        <h2 className="font-semibold mb-2">Workflows (act)</h2>
        <p className="text-slate-400 text-sm">Chargement...</p>
      </section>
    );
  }

  const grouped = jobs.reduce<Record<string, WorkflowJob[]>>((acc, j) => {
    const k = j.workflow_file ?? "";
    if (!acc[k]) acc[k] = [];
    acc[k].push(j);
    return acc;
  }, {});
  const groups = Object.entries(grouped);

  return (
    <section className="panel">
      <h2 className="font-semibold text-lg mb-3">Workflows disponibles</h2>
      {error && (
        <p className="text-amber-400 text-sm mb-3">
          {error}
          {!error.includes("container") && !error.includes("disabled") && (
            <span className="block mt-1 text-slate-500">
              Vérifier{" "}
              <code className="bg-slate-900 px-1 rounded">
                ACT_ENABLED=true
              </code>
              .
            </span>
          )}
        </p>
      )}
      {jobs.length === 0 && !error && (
        <p className="text-slate-400 text-sm">
          Aucun workflow dans .github/workflows de ce conteneur.
        </p>
      )}
      {groups.map(([wfFile, groupJobs]) => (
        <div key={wfFile} className="workflow-group mb-4">
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            {wfFile}
          </h3>
          <ul className="space-y-2">
            {groupJobs.map((j) => {
              const key = `${j.workflow_file ?? ""}:${j.job}`;
              const href = `/containers/${encodeURIComponent(containerId)}/workflows/${encodeURIComponent(j.workflow_file)}?job=${encodeURIComponent(j.job)}`;
              return (
                <li key={key}>
                  <Link
                    href={href}
                    className="workflow-job-card workflow-job-link"
                  >
                    <span className="font-medium">{j.job}</span>
                    <span className="text-slate-500 ml-2">→</span>
                    {j.workflow && (
                      <p className="text-xs text-slate-500 mt-0.5">
                        {j.workflow}
                      </p>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </section>
  );
}
