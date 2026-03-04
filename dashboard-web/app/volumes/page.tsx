"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiJson, ApiClientError, apiFetch } from "../lib/api-client";
import { useAuth } from "../contexts/auth-context";
import { useConfirm } from "../components/confirm-dialog";
import { useNotifications } from "../components/notifications";

interface VolumeItem {
  name: string;
  driver: string;
  labels: Record<string, string>;
  mountpoint: string;
  created_at: string;
}

export default function VolumesPage() {
  const { isAdmin } = useAuth();
  const notify = useNotifications();
  const confirm = useConfirm();
  const [volumes, setVolumes] = useState<VolumeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingName, setDeletingName] = useState<string | null>(null);

  const fetchVolumes = useCallback(
    async (isRefresh = false): Promise<VolumeItem[]> => {
      if (!isRefresh) setLoading(true);
      try {
        const data = await apiJson<VolumeItem[]>("/api/volumes");
        setVolumes(data);
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
    void fetchVolumes();
  }, [fetchVolumes]);

  const deleteVolume = async (vol: VolumeItem) => {
    const confirmed = await confirm({
      title: "Supprimer le volume",
      message: `Supprimer le volume ${vol.name} ? Les données seront perdues. Cette action est irréversible.`,
      confirmLabel: "Supprimer",
      cancelLabel: "Annuler",
      tone: "danger",
      requireText: "SUPPRIMER",
      inputLabel: "Pour confirmer, tapez",
      inputPlaceholder: "SUPPRIMER",
      delaySeconds: 3,
    });
    if (!confirmed) return;
    setDeletingName(vol.name);
    try {
      await apiFetch(
        `/api/volumes/${encodeURIComponent(vol.name)}?force=false`,
        {
          method: "DELETE",
        }
      );
      await fetchVolumes();
      notify.info(`Volume ${vol.name} supprimé`);
    } catch (e) {
      notify.error(e instanceof ApiClientError ? e.message : "Erreur");
    } finally {
      setDeletingName(null);
    }
  };

  const onRefresh = () => {
    setRefreshing(true);
    void fetchVolumes(true);
  };

  if (loading)
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <div className="page-header mb-6">
          <h1 className="page-title text-2xl font-bold">Volumes Docker</h1>
        </div>
        <div className="loading-placeholder">
          <div className="loading-placeholder__spinner" aria-hidden />
          <p className="loading-placeholder__text">Chargement des volumes…</p>
        </div>
      </main>
    );

  if (error)
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <div className="page-header mb-6">
          <h1 className="page-title text-2xl font-bold">Volumes Docker</h1>
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
              void fetchVolumes();
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
        <h1 className="page-title text-2xl font-bold">Volumes Docker</h1>
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
        {volumes.length === 0 ? (
          <li className="empty-state">
            <span className="empty-state__icon" aria-hidden>
              💾
            </span>
            <p className="empty-state__text">Aucun volume</p>
          </li>
        ) : (
          volumes.map((vol) => (
            <li key={vol.name} className="volume-card">
              <div className="container-card__main">
                <div className="container-card__info">
                  <div className="container-card__header">
                    <p className="container-card__name">{vol.name}</p>
                  </div>
                  <p className="container-card__link">
                    <Link href={`/volumes/${encodeURIComponent(vol.name)}`}>
                      Voir les détails
                    </Link>
                  </p>
                  <p className="container-card__image">Driver : {vol.driver}</p>
                  {vol.created_at && (
                    <p className="text-xs text-slate-500 mt-1">
                      Créé : {new Date(vol.created_at).toLocaleString()}
                    </p>
                  )}
                </div>
              </div>
              {isAdmin && (
                <div className="container-card__actions">
                  <button
                    type="button"
                    onClick={() => void deleteVolume(vol)}
                    disabled={deletingName === vol.name}
                    className="container-btn container-btn--delete"
                  >
                    {deletingName === vol.name ? "Suppression…" : "Supprimer"}
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
