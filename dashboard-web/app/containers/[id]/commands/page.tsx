"use client";

import Link from "next/link";
import { useMemo } from "react";
import { ContainerCommandsPanel } from "../components/container-commands-panel";

export default function ContainerCommandsPage({
  params,
}: {
  params: { id: string };
}) {
  const containerId = useMemo(() => params.id, [params.id]);

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">
          Commandes du conteneur
        </h1>
        <div className="top-nav">
          <Link href={`/containers/${encodeURIComponent(containerId)}`}>
            Vue generale
          </Link>
          <Link href={`/containers/${encodeURIComponent(containerId)}/logs`}>
            Logs
          </Link>
          <Link
            href={`/containers/${encodeURIComponent(containerId)}/environment`}
          >
            Environnement
          </Link>
        </div>
      </div>
      <ContainerCommandsPanel containerId={containerId} />
    </main>
  );
}
