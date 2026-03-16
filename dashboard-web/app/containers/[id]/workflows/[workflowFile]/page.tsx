"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { LogSnapshot } from "../../../../components/log-snapshot";
import { apiJson, streamSsePost } from "../../../../lib/api-client";
import { useAuth } from "../../../../contexts/auth-context";
import { useNotifications } from "../../../../components/notifications";

interface WorkflowJob {
  workflow: string;
  workflow_file: string;
  job: string;
}

export default function WorkflowDetailPage({
  params,
  searchParams = {},
}: {
  params: { id: string; workflowFile: string };
  searchParams?: { job?: string };
}) {
  const containerId = params.id;
  const workflowFile = params.workflowFile;
  const jobParam = searchParams?.job;
  const preSelectedJob = typeof jobParam === "string" ? jobParam : null;

  const { isAdmin } = useAuth();
  const notify = useNotifications();
  const [jobs, setJobs] = useState<WorkflowJob[]>([]);
  const [codeContent, setCodeContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningJob, setRunningJob] = useState<string | null>(null);
  const [output, setOutput] = useState<string[]>([]);
  const outputRef = useRef<HTMLDivElement | null>(null);
  const stopStreamRef = useRef<(() => void) | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [listRes, contentRes] = await Promise.all([
        apiJson<unknown>(
          `/api/workflows?container_id=${encodeURIComponent(containerId)}`
        ),
        apiJson<{ content: string }>(
          `/api/workflows/content?workflow_file=${encodeURIComponent(workflowFile)}&container_id=${encodeURIComponent(containerId)}`
        ),
      ]);

      const list = Array.isArray(listRes) ? listRes : [];
      const filtered = list.filter(
        (j): j is WorkflowJob =>
          j != null &&
          typeof j === "object" &&
          typeof (j as WorkflowJob).job === "string" &&
          (j as WorkflowJob).workflow_file === workflowFile
      );
      setJobs(filtered);
      setCodeContent(contentRes.content ?? "");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setJobs([]);
      setCodeContent(null);
    } finally {
      setLoading(false);
    }
  }, [containerId, workflowFile]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    if (outputRef.current && output.length > 0) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [output]);

  useEffect(() => () => stopStreamRef.current?.(), []);

  const onRunJob = (job: WorkflowJob) => {
    stopStreamRef.current?.();
    setRunningJob(job.job);
    setOutput([]);
    stopStreamRef.current = streamSsePost(
      "/api/workflows/run",
      {
        job: job.job,
        workflow_file: job.workflow_file,
        container_id: containerId,
      },
      {
        onEvent: (eventType, data) => {
          const d = data as { line?: string; code?: number; message?: string };
          const line = d.line;
          if (eventType === "output" && typeof line === "string") {
            setOutput((prev) => [...prev, line]);
          } else if (eventType === "exit") {
            const code = typeof d.code === "number" ? d.code : 0;
            setRunningJob(null);
            notify[code === 0 ? "success" : "error"](
              `Job ${job.job} terminé (exit ${code})`
            );
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
  };

  const listHref = `/containers/${encodeURIComponent(containerId)}/workflows`;

  if (loading) {
    return (
      <main className="page-shell p-4 max-w-6xl mx-auto space-y-4">
        <div className="page-header">
          <h1 className="page-title text-2xl font-bold">{workflowFile}</h1>
          <nav className="top-nav" aria-label="Navigation">
            <Link href={listHref}>← Liste des workflows</Link>
          </nav>
        </div>
        <section className="panel">
          <p className="text-slate-400 text-sm">Chargement…</p>
        </section>
      </main>
    );
  }

  if (error) {
    return (
      <main className="page-shell p-4 max-w-6xl mx-auto space-y-4">
        <div className="page-header">
          <h1 className="page-title text-2xl font-bold">{workflowFile}</h1>
          <nav className="top-nav">
            <Link href={listHref}>← Liste des workflows</Link>
          </nav>
        </div>
        <section className="panel">
          <p className="text-amber-400">{error}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell p-4 max-w-6xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">{workflowFile}</h1>
        <nav className="top-nav" aria-label="Navigation conteneur">
          <Link href={`/containers/${encodeURIComponent(containerId)}`}>
            Vue générale
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/commands`}
          >
            Commandes
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/workflows`}
          >
            Workflows
          </Link>
          <Link href={`/containers/${encodeURIComponent(containerId)}/logs`}>
            Logs
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/environment`}
          >
            Environnement
          </Link>
        </nav>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <Link
          href={listHref}
          className="text-sm text-slate-500 hover:text-slate-300"
        >
          ← Liste des workflows
        </Link>
      </div>

      <section className="panel mb-4">
        <h2 className="font-semibold mb-2">Code YAML</h2>
        <div className="code-block">
          <div className="code-block-header">
            .github/workflows/{workflowFile}
          </div>
          <pre className="code-block-content">{codeContent}</pre>
        </div>
      </section>

      <section className="panel mb-4">
        <h2 className="font-semibold mb-3">Jobs</h2>
        {jobs.length === 0 ? (
          <p className="text-slate-400 text-sm">
            Aucun job trouvé dans ce workflow.
          </p>
        ) : (
          <ul className="space-y-2">
            {jobs.map((j) => {
              const isRunning = runningJob === j.job;
              const isPreselected = preSelectedJob === j.job;
              return (
                <li
                  key={j.job}
                  className={`workflow-job-card${isPreselected ? " workflow-job-card-preselected" : ""}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <span className="font-medium">{j.job}</span>
                      {j.workflow && (
                        <span className="text-slate-500 text-sm ml-2">
                          {j.workflow}
                        </span>
                      )}
                    </div>
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={() => onRunJob(j)}
                        disabled={isRunning || runningJob != null}
                        className="btn btn-primary px-3 py-1 text-xs disabled:opacity-60 disabled:cursor-not-allowed shrink-0"
                      >
                        {isRunning ? "En cours…" : "Exécuter"}
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {output.length > 0 && (
        <section className="panel">
          <LogSnapshot
            lines={output}
            title="Sortie"
            subtitle="Terminal du job workflow en cours d'exécution."
            maxHeightClassName="max-h-64"
            viewportRef={outputRef}
            ariaLive="polite"
          />
        </section>
      )}
    </main>
  );
}
