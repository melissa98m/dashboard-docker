"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiJson, ApiClientError, apiFetch } from "../../lib/api-client";
import { useAuth } from "../../contexts/auth-context";
import { useConfirm } from "../../components/confirm-dialog";
import { useNotifications } from "../../components/notifications";

interface ImageDetail {
  id: string;
  tags: string[];
  display_name: string;
  size: number;
  size_human: string;
  created: string;
  labels: Record<string, string>;
  architecture: string;
  os: string;
  parent: string;
}

export default function ImageDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { isAdmin } = useAuth();
  const notify = useNotifications();
  const confirm = useConfirm();
  const imageId = useMemo(() => params.id, [params.id]);
  const [detail, setDetail] = useState<ImageDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(async () => {
    setError(null);
    try {
      const data = await apiJson<ImageDetail>(
        `/api/images/${encodeURIComponent(imageId)}`
      );
      setDetail(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    }
  }, [imageId]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  const deleteImage = async () => {
    if (!detail) return;
    const confirmed = await confirm({
      title: "Supprimer l'image",
      message: `Supprimer ${detail.display_name} ? Cette action est irréversible.`,
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
      await apiFetch(`/api/images/${encodeURIComponent(imageId)}?force=false`, {
        method: "DELETE",
      });
      notify.info(`Image ${detail.display_name} supprimée`);
      window.location.href = "/images";
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
          <Link href="/images" className="btn btn-neutral px-4 py-2">
            Retour à la liste
          </Link>
        </div>
      </main>
    );
  }

  if (!detail) {
    return <main className="page-shell p-4">Chargement…</main>;
  }

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">{detail.display_name}</h1>
        <div className="flex items-center gap-3">
          <Link href="/images" className="btn btn-neutral px-3 py-1.5 text-sm">
            ← Liste des images
          </Link>
          {isAdmin && (
            <button
              type="button"
              onClick={() => void deleteImage()}
              className="container-btn container-btn--delete"
            >
              Supprimer
            </button>
          )}
        </div>
      </div>

      <section className="panel">
        <h2 className="font-semibold">Vue générale</h2>
        <p className="text-slate-400 text-sm">ID : {detail.id}</p>
        <p className="mt-2">
          Taille : {detail.size_human} • {detail.architecture}/{detail.os}
        </p>
        {detail.created && (
          <p className="text-xs text-slate-400 mt-1">
            Créée : {new Date(detail.created).toLocaleString()}
          </p>
        )}
      </section>

      {detail.tags.length > 0 && (
        <section className="panel">
          <h2 className="font-semibold mb-2">Tags</h2>
          <ul className="list-disc list-inside text-sm">
            {detail.tags.map((tag) => (
              <li key={tag}>{tag}</li>
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

      {detail.parent && (
        <section className="panel">
          <h2 className="font-semibold">Image parente</h2>
          <p className="text-sm font-mono text-slate-400">{detail.parent}</p>
        </section>
      )}
    </main>
  );
}
