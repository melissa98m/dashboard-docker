"use client";

import Link from "next/link";
import { useMemo } from "react";
import { ContainerWorkflowsPanel } from "../components/container-workflows-panel";

export default function ContainerWorkflowsPage({
  params,
}: {
  params: { id: string };
}) {
  const containerId = useMemo(() => params.id, [params.id]);

  return (
    <main className="page-shell p-4 max-w-6xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">
          Workflows GitHub Actions
        </h1>
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
            className="is-active"
            aria-current="page"
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
      <ContainerWorkflowsPanel containerId={containerId} />
    </main>
  );
}
