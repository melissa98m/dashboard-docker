"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiJson, ApiClientError, apiFetch } from "../../lib/api-client";
import { useAuth } from "../../contexts/auth-context";
import { useConfirm } from "../../components/confirm-dialog";
import { useNotifications } from "../../components/notifications";

interface ContainerRef {
  id: string;
  name: string;
}

interface VolumeDetail {
  name: string;
  driver: string;
  mountpoint: string;
  labels: Record<string, string>;
  created_at: string;
  scope: string;
  containers_using: ContainerRef[];
}

export default function VolumeDetailPage({
  params,
}: {
  params: { name: string };
}) {
  const { isAdmin } = useAuth();
  const notify = useNotifications();
  const confirm = useConfirm();
  const volumeName = useMemo(() => params.name, [params.name]);
  const [detail, setDetail] = useState<VolumeDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(async () => {
    setError(null);
    try {
      const data = await apiJson<VolumeDetail>(
        `/api/volumes/${encodeURIComponent(volumeName)}`
      );
      setDetail(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    }
  }, [volumeName]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  const deleteVolume = async () => {
    if (!detail) return;
    const confirmed = await confirm({
      title: "Supprimer le volume",
      message: `Supprimer le volume ${detail.name} ? Les données seront perdues. Cette action est irréversible.`,
      confirmLabel: "Supprimer",
      cancelLabel: "Annuler",
      tone: "danger",
      requireText: "SUPPRIMER",
      inputLabel: "Pour confirmer, tapez",
      inputPlaceholder: "SUPPRIMER",
      delaySeconds: 3,
    });
    if (!confirmed) return;
    try {
      await apiFetch(
        `/api/volumes/${encodeURIComponent(volumeName)}?force=false`,
        {
          method: "DELETE",
        }
      );
      notify.info(`Volume ${detail.name} supprimé`);
      window.location.href = "/volumes";
    } catch (e) {
      notify.error(e instanceof ApiClientError ? e.message : "Erreur");
    }
  };

  if (error) {
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
        <p className="text-red-400">Erreur : {error}</p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => void loadDetail()}
            className="btn btn-neutral px-4 py-2"
          >
            Réessayer
          </button>
          <Link href="/volumes" className="btn btn-neutral px-4 py-2">
            Retour à la liste
          </Link>
        </div>
      </main>
    );
  }

  if (!detail) {
    return <main className="page-shell p-4">Chargement…</main>;
  }

  const hasContainersUsing = detail.containers_using.length > 0;

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">{detail.name}</h1>
        <div className="flex items-center gap-3">
          <Link href="/volumes" className="btn btn-neutral px-3 py-1.5 text-sm">
            ← Liste des volumes
          </Link>
          {isAdmin && (
            <button
              type="button"
              onClick={() => void deleteVolume()}
              disabled={hasContainersUsing}
              className="container-btn container-btn--delete disabled:opacity-50"
              title={
                hasContainersUsing
                  ? "Impossible de supprimer : volume utilisé par des conteneurs"
                  : undefined
              }
            >
              Supprimer
            </button>
          )}
        </div>
      </div>

      <section className="panel">
        <h2 className="font-semibold">Vue générale</h2>
        <p className="text-slate-400 text-sm">Driver : {detail.driver}</p>
        <p className="mt-2">Scope : {detail.scope}</p>
        {detail.mountpoint && (
          <p className="text-xs font-mono text-slate-500 mt-1 break-all">
            Mountpoint : {detail.mountpoint}
          </p>
        )}
        {detail.created_at && (
          <p className="text-xs text-slate-400 mt-1">
            Créé : {new Date(detail.created_at).toLocaleString()}
          </p>
        )}
      </section>

      {hasContainersUsing && (
        <section className="panel">
          <h2 className="font-semibold mb-2">Conteneurs utilisant ce volume</h2>
          <ul className="space-y-1">
            {detail.containers_using.map((c) => (
              <li key={c.id}>
                <Link
                  href={`/containers/${encodeURIComponent(c.id)}`}
                  className="text-sky-400 hover:underline"
                >
                  {c.name} ({c.id})
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {Object.keys(detail.labels).length > 0 && (
        <section className="panel">
          <h2 className="font-semibold mb-2">Labels</h2>
          <dl className="text-sm space-y-1">
            {Object.entries(detail.labels).map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <dt className="text-slate-400">{k}:</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </main>
  );
}
