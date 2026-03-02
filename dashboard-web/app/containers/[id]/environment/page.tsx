"use client";

import Link from "next/link";
import { useMemo } from "react";
import { ContainerEnvEditor } from "../components/container-env-editor";

export default function ContainerEnvironmentPage({
  params,
}: {
  params: { id: string };
}) {
  const containerId = useMemo(() => params.id, [params.id]);

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">Variables d&apos;environnement</h1>
        <div className="top-nav">
          <Link href={`/containers/${encodeURIComponent(containerId)}`}>Vue generale</Link>
          <Link href={`/containers/${encodeURIComponent(containerId)}/logs`}>Logs</Link>
          <Link href={`/containers/${encodeURIComponent(containerId)}/commands`}>Commandes</Link>
        </div>
      </div>
      <ContainerEnvEditor containerId={containerId} />
    </main>
  );
}
