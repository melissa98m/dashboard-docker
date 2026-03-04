"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiJson, ApiClientError, apiFetch } from "../lib/api-client";
import { useAuth } from "../contexts/auth-context";
import { useConfirm } from "../components/confirm-dialog";
import { useNotifications } from "../components/notifications";

interface ImageItem {
  id: string;
  tags: string[];
  display_name: string;
  size: number;
  size_human: string;
  created: string;
}

export default function ImagesPage() {
  const { isAdmin } = useAuth();
  const notify = useNotifications();
  const confirm = useConfirm();
  const [images, setImages] = useState<ImageItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchImages = useCallback(
    async (isRefresh = false): Promise<ImageItem[]> => {
      if (!isRefresh) setLoading(true);
      try {
        const data = await apiJson<ImageItem[]>("/api/images");
        setImages(data);
        return data;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erreur");
        return [];
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    []
  );

  useEffect(() => {
    void fetchImages();
  }, [fetchImages]);

  const deleteImage = async (img: ImageItem) => {
    const confirmed = await confirm({
      title: "Supprimer l'image",
      message: `Supprimer ${img.display_name} ? Cette action est irréversible.`,
      confirmLabel: "Supprimer",
      cancelLabel: "Annuler",
      tone: "danger",
      requireText: "SUPPRIMER",
      inputLabel: "Pour confirmer, tapez",
      inputPlaceholder: "SUPPRIMER",
      delaySeconds: 3,
    });
    if (!confirmed) return;
    setDeletingId(img.id);
    try {
      await apiFetch(`/api/images/${encodeURIComponent(img.id)}?force=false`, {
        method: "DELETE",
      });
      await fetchImages();
      notify.info(`Image ${img.display_name} supprimée`);
    } catch (e) {
      notify.error(e instanceof ApiClientError ? e.message : "Erreur");
    } finally {
      setDeletingId(null);
    }
  };

  const onRefresh = () => {
    setRefreshing(true);
    void fetchImages(true);
  };

  if (loading)
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <div className="page-header mb-6">
          <h1 className="page-title text-2xl font-bold">Images Docker</h1>
        </div>
        <div className="loading-placeholder">
          <div className="loading-placeholder__spinner" aria-hidden />
          <p className="loading-placeholder__text">Chargement des images…</p>
        </div>
      </main>
    );

  if (error)
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <div className="page-header mb-6">
          <h1 className="page-title text-2xl font-bold">Images Docker</h1>
        </div>
        <div className="error-state">
          <span className="error-state__icon" aria-hidden>
            ⚠
          </span>
          <p className="error-state__message">Erreur : {error}</p>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setLoading(true);
              void fetchImages();
            }}
            className="btn btn-neutral mt-3 px-4 py-2"
          >
            Réessayer
          </button>
        </div>
      </main>
    );

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto">
      <div className="page-header mb-6">
        <h1 className="page-title text-2xl font-bold">Images Docker</h1>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="btn btn-neutral px-3 py-1.5 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {refreshing ? "Rafraîchissement…" : "Rafraîchir"}
          </button>
        </div>
      </div>

      <ul className="containers-list" role="list">
        {images.length === 0 ? (
          <li className="empty-state">
            <span className="empty-state__icon" aria-hidden>
              🖼
            </span>
            <p className="empty-state__text">Aucune image</p>
          </li>
        ) : (
          images.map((img) => (
            <li key={img.id} className="image-card">
              <div className="container-card__main">
                <div className="container-card__info">
                  <div className="container-card__header">
                    <p className="container-card__name">{img.display_name}</p>
                  </div>
                  <p className="container-card__link">
                    <Link href={`/images/${encodeURIComponent(img.id)}`}>
                      Voir les détails
                    </Link>
                  </p>
                  <p className="container-card__image">
                    {img.size_human} •{" "}
                    {img.tags.length > 1 ? `${img.tags.length} tags` : ""}
                  </p>
                  {img.created && (
                    <p className="text-xs text-slate-500 mt-1">
                      Créée : {new Date(img.created).toLocaleString()}
                    </p>
                  )}
                </div>
              </div>
              {isAdmin && (
                <div className="container-card__actions">
                  <button
                    type="button"
                    onClick={() => void deleteImage(img)}
                    disabled={deletingId === img.id}
                    className="container-btn container-btn--delete"
                  >
                    {deletingId === img.id ? "Suppression…" : "Supprimer"}
                  </button>
                </div>
              )}
            </li>
          ))
        )}
      </ul>
    </main>
  );
}
