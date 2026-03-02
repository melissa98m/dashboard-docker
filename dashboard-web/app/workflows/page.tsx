"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch, apiJson, streamSsePost } from "../lib/api-client";
import { useNotifications } from "../components/notifications";

interface WorkflowJob {
  workflow: string;
  workflow_file: string;
  job: string;
}

export default function WorkflowsPage() {
  const notify = useNotifications();
  const [jobs, setJobs] = useState<WorkflowJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningJob, setRunningJob] = useState<string | null>(null);
  const [output, setOutput] = useState<string[]>([]);
  const outputRef = useRef<HTMLPreElement | null>(null);
  const stopStreamRef = useRef<(() => void) | null>(null);

  const loadJobs = async () => {
    setLoading(true);
    try {
      const data = await apiJson<WorkflowJob[]>("/api/workflows");
      setJobs(Array.isArray(data) ? data : []);
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erreur de chargement";
      setError(msg);
      if (msg.includes("disabled") || msg.includes("503")) {
        setJobs([]);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadJobs();
  }, []);

  useEffect(() => {
    if (outputRef.current && output.length > 0) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [output]);

  useEffect(() => () => stopStreamRef.current?.(), []);

  const onRunJob = async (job: WorkflowJob) => {
    stopStreamRef.current?.();
    const key = `${job.workflow_file}:${job.job}`;
    setRunningJob(key);
    setOutput([]);
    stopStreamRef.current = streamSsePost(
      "/api/workflows/run",
      { job: job.job, workflow_file: job.workflow_file },
      {
        onEvent: (eventType, data) => {
          const d = data as { line?: string; code?: number; message?: string };
          const line = d.line;
          if (eventType === "output" && typeof line === "string") {
            setOutput((prev) => [...prev, line]);
          } else if (eventType === "exit") {
            const code = typeof d.code === "number" ? d.code : 0;
            setRunningJob(null);
            notify[code === 0 ? "success" : "error"](`Job ${job.job} terminé (exit ${code})`);
          } else if (eventType === "error") {
            setRunningJob(null);
            notify.error(d.message || "Erreur act");
          }
        },
        onError: (err) => {
          setRunningJob(null);
          notify.error(err.message);
        },
      }
    );
    stopStreamRef.current = stop;
  };

  if (loading) {
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <p className="text-slate-400">Chargement...</p>
      </main>
    );
  }

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">Workflows GitHub Actions (act)</h1>
      </div>

      {error && (
        <section className="panel">
          <p className="text-amber-400">{error}</p>
          <p className="text-slate-400 text-sm mt-2">
            Definir <code className="bg-slate-800 px-1 rounded">ACT_ENABLED=true</code> et monter le
            depot dans <code className="bg-slate-800 px-1 rounded">/workspace</code>.
          </p>
        </section>
      )}

      {jobs.length === 0 && !error && (
        <section className="panel">
          <p className="text-slate-400">Aucun workflow trouvé dans .github/workflows/</p>
        </section>
      )}

      {jobs.length > 0 && (
        <section className="panel">
          <h2 className="font-semibold mb-2">Jobs disponibles</h2>
          <ul className="space-y-2">
            {jobs.map((j) => {
              const key = `${j.workflow_file}:${j.job}`;
              const isRunning = runningJob === key;
              return (
                <li key={key} className="entity-card flex items-center justify-between gap-2">
                  <div>
                    <p className="font-medium">{j.job}</p>
                    <p className="text-xs text-slate-400">
                      {j.workflow} — {j.workflow_file}
                    </p>
                  </div>
                  <button
                    onClick={() => void onRunJob(j)}
                    disabled={isRunning || runningJob != null}
                    className="btn btn-primary px-3 py-1 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {isRunning ? "En cours..." : "Executer"}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {output.length > 0 && (
        <section className="panel">
          <h2 className="font-semibold mb-2">Sortie</h2>
          <pre
            ref={outputRef}
            className="text-xs overflow-x-auto max-h-64 overflow-y-auto rounded bg-slate-900 p-3 font-mono text-slate-300 whitespace-pre-wrap"
          >
            {output.join("\n")}
          </pre>
        </section>
      )}
    </main>
  );
}
