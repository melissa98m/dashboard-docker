"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  EnvProfileResponse,
  applyContainerEnvProfile,
  getContainerEnvProfile,
  updateContainerEnvProfile,
} from "../../../lib/container-env-api";
import { useConfirm } from "../../../components/confirm-dialog";
import { EnvVarRow } from "./env-var-row";

type DraftMap = Record<string, { value: string; sensitive: boolean }>;

function toDraftMap(profile: EnvProfileResponse): DraftMap {
  const map: DraftMap = {};
  profile.env.forEach((item) => {
    map[item.key] = { value: item.value, sensitive: item.sensitive };
  });
  return map;
}

function hasDifferences(a: DraftMap, b: DraftMap): boolean {
  const aKeys = Object.keys(a).sort();
  const bKeys = Object.keys(b).sort();
  if (aKeys.length !== bKeys.length) {
    return true;
  }
  for (let i = 0; i < aKeys.length; i += 1) {
    const key = aKeys[i];
    if (key !== bKeys[i]) {
      return true;
    }
    if (a[key].value !== b[key].value) {
      return true;
    }
  }
  return false;
}

export function ContainerEnvEditor({ containerId }: { containerId: string }) {
  const confirm = useConfirm();
  const [profile, setProfile] = useState<EnvProfileResponse | null>(null);
  const [draft, setDraft] = useState<DraftMap>({});
  const [baseDraft, setBaseDraft] = useState<DraftMap>({});
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const dirty = useMemo(
    () => hasDifferences(draft, baseDraft),
    [draft, baseDraft]
  );

  const loadProfile = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await getContainerEnvProfile(containerId);
      setProfile(response);
      const nextDraft = toDraftMap(response);
      setDraft(nextDraft);
      setBaseDraft(nextDraft);
      setVisibleKeys({});
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Erreur de chargement des variables"
      );
    } finally {
      setBusy(false);
    }
  }, [containerId]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const sortedKeys = useMemo(() => Object.keys(draft).sort(), [draft]);
  const filteredKeys = useMemo(
    () =>
      sortedKeys.filter((key) =>
        key.toLowerCase().includes(search.trim().toLowerCase())
      ),
    [sortedKeys, search]
  );

  const setValue = (key: string, value: string) => {
    setDraft((previous) => ({
      ...previous,
      [key]: { ...previous[key], value },
    }));
  };

  const removeKey = (key: string) => {
    setDraft((previous) => {
      const cloned = { ...previous };
      delete cloned[key];
      return cloned;
    });
    setVisibleKeys((previous) => {
      const cloned = { ...previous };
      delete cloned[key];
      return cloned;
    });
  };

  const addVariable = () => {
    const trimmedKey = newKey.trim().toUpperCase();
    if (!trimmedKey) {
      setError("La clé est obligatoire");
      return;
    }
    if (draft[trimmedKey]) {
      setError("Cette clé existe déjà");
      return;
    }
    setDraft((previous) => ({
      ...previous,
      [trimmedKey]: {
        value: newValue,
        sensitive: /(token|secret|password|api[_-]?key|pwd|auth)/i.test(
          trimmedKey
        ),
      },
    }));
    setNewKey("");
    setNewValue("");
    setError(null);
  };

  const saveChanges = async () => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const removedKeys = Object.keys(baseDraft).filter((key) => !draft[key]);
      const setPayload: Record<string, string> = {};
      Object.keys(draft).forEach((key) => {
        if (!baseDraft[key] || baseDraft[key].value !== draft[key].value) {
          setPayload[key] = draft[key].value;
        }
      });
      const updated = await updateContainerEnvProfile(containerId, {
        mode: "merge",
        set: setPayload,
        unset: removedKeys,
      });
      const nextDraft = toDraftMap(updated);
      setProfile(updated);
      setDraft(nextDraft);
      setBaseDraft(nextDraft);
      setVisibleKeys({});
      setInfo(
        "Variables enregistrées. Clique sur Appliquer pour recréer le conteneur."
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de sauvegarde");
    } finally {
      setBusy(false);
    }
  };

  const applyChanges = async () => {
    const confirmed = await confirm({
      title: "Appliquer la configuration",
      message:
        "Appliquer les changements d’environnement va recréer ce conteneur. Continuer ?",
      confirmLabel: "Appliquer",
      cancelLabel: "Annuler",
      tone: "danger",
      requireText: "APPLIQUER",
      inputLabel: "Pour confirmer, tapez",
      inputPlaceholder: "APPLIQUER",
      delaySeconds: 3,
    });
    if (!confirmed) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const response = await applyContainerEnvProfile(containerId, false);
      setInfo(
        response.new_container_id
          ? `Appliqué. Nouveau conteneur: ${response.new_container_id}`
          : "Appliqué."
      );
      await loadProfile();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de l'application");
    } finally {
      setBusy(false);
    }
  };

  if (busy && profile == null) {
    return (
      <p className="text-sm text-slate-400">
        Chargement des variables d’environnement...
      </p>
    );
  }

  return (
    <section className="panel bg-slate-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">Variables d’environnement</h2>
        <div className="text-xs text-slate-400">
          source: {profile?.source_mode ?? "n/a"}{" "}
          {profile?.writable ? "(modifiable)" : "(lecture seule)"}
        </div>
      </div>
      {profile?.detected_env_file && (
        <p className="text-xs text-slate-400 break-all">
          fichier détecté: {profile.detected_env_file}
        </p>
      )}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <label>
          <span className="field-label">Nouvelle cle</span>
          <input
            value={newKey}
            onChange={(event) => setNewKey(event.target.value)}
            placeholder="Nouvelle clé"
            className="w-full px-2 py-1 rounded bg-slate-900 border border-slate-700 text-xs"
          />
        </label>
        <label>
          <span className="field-label">Valeur</span>
          <input
            value={newValue}
            onChange={(event) => setNewValue(event.target.value)}
            placeholder="Valeur"
            className="w-full px-2 py-1 rounded bg-slate-900 border border-slate-700 text-xs"
          />
        </label>
        <button
          type="button"
          onClick={addVariable}
          className="px-3 py-1 rounded bg-emerald-700 hover:bg-emerald-600 text-sm"
        >
          Ajouter
        </button>
      </div>
      <label>
        <span className="field-label">Recherche variable</span>
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Rechercher une variable"
          className="w-full px-2 py-1 rounded bg-slate-900 border border-slate-700 text-xs"
        />
      </label>
      <div className="overflow-auto max-h-72">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-700 text-xs text-slate-400">
              <th className="py-2 pr-2">Clé</th>
              <th className="py-2 px-2">Valeur</th>
              <th className="py-2 pl-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredKeys.map((key) => (
              <EnvVarRow
                key={key}
                envKey={key}
                value={draft[key].value}
                sensitive={draft[key].sensitive}
                visible={Boolean(visibleKeys[key])}
                changed={
                  !baseDraft[key] || baseDraft[key].value !== draft[key].value
                }
                onValueChange={(value) => setValue(key, value)}
                onDelete={() => removeKey(key)}
                onToggleVisibility={() =>
                  setVisibleKeys((previous) => ({
                    ...previous,
                    [key]: !previous[key],
                  }))
                }
              />
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!dirty || busy}
          onClick={saveChanges}
          className="px-3 py-1 rounded bg-sky-700 hover:bg-sky-600 disabled:opacity-60"
        >
          Sauvegarder le brouillon
        </button>
        <button
          type="button"
          disabled={busy || !profile?.pending_apply}
          onClick={applyChanges}
          className="px-3 py-1 rounded bg-amber-700 hover:bg-amber-600 disabled:opacity-60"
        >
          Appliquer (recreate)
        </button>
        <button
          type="button"
          disabled={busy || !dirty}
          onClick={() => {
            setDraft(baseDraft);
            setVisibleKeys({});
          }}
          className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-60"
        >
          Réinitialiser
        </button>
      </div>
      {error && <p className="text-sm text-red-400">Erreur: {error}</p>}
      {info && <p className="text-sm text-emerald-300">{info}</p>}
    </section>
  );
}
