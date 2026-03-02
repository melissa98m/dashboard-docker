"use client";

interface EnvVarRowProps {
  envKey: string;
  value: string;
  sensitive: boolean;
  visible: boolean;
  changed: boolean;
  onValueChange: (next: string) => void;
  onDelete: () => void;
  onToggleVisibility: () => void;
}

export function EnvVarRow({
  envKey,
  value,
  sensitive,
  visible,
  changed,
  onValueChange,
  onDelete,
  onToggleVisibility,
}: EnvVarRowProps) {
  return (
    <tr className="border-b border-slate-700">
      <td className="py-2 pr-2 align-top text-xs text-slate-300 break-all">{envKey}</td>
      <td className="py-2 px-2 align-top">
        <input
          value={value}
          onChange={(event) => onValueChange(event.target.value)}
          type={sensitive && !visible ? "password" : "text"}
          className="w-full px-2 py-1 rounded bg-slate-900 border border-slate-700 text-xs"
        />
      </td>
      <td className="py-2 pl-2 align-top">
        <div className="flex gap-2 justify-end">
          {sensitive && (
            <button
              type="button"
              onClick={onToggleVisibility}
              className="text-xs px-2 py-1 rounded bg-slate-700 hover:bg-slate-600"
            >
              {visible ? "Masquer" : "Afficher"}
            </button>
          )}
          <button
            type="button"
            onClick={onDelete}
            className="text-xs px-2 py-1 rounded bg-red-700 hover:bg-red-600"
          >
            Supprimer
          </button>
          {changed && (
            <span className="text-[10px] px-2 py-1 rounded bg-amber-700/30 text-amber-300">
              modifiée
            </span>
          )}
        </div>
      </td>
    </tr>
  );
}
