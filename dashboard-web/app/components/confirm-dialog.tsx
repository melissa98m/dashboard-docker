"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useEffect } from "react";

type ConfirmTone = "neutral" | "danger";

interface ConfirmRequest {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  tone: ConfirmTone;
  requireText: string | null;
  inputLabel: string;
  inputPlaceholder: string;
  delaySeconds: number;
}

interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: ConfirmTone;
  requireText?: string;
  inputLabel?: string;
  inputPlaceholder?: string;
  delaySeconds?: number;
}

interface ConfirmContextValue {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

const ConfirmDialogContext = createContext<ConfirmContextValue | null>(null);

function normalizeOptions(options: ConfirmOptions): ConfirmRequest {
  return {
    title: options.title ?? "Confirmer l'action",
    message: options.message,
    confirmLabel: options.confirmLabel ?? "Confirmer",
    cancelLabel: options.cancelLabel ?? "Annuler",
    tone: options.tone ?? "neutral",
    requireText: options.requireText ?? null,
    inputLabel: options.inputLabel ?? "Saisie de verification",
    inputPlaceholder: options.inputPlaceholder ?? "Tapez la valeur demandee",
    delaySeconds: Math.max(0, options.delaySeconds ?? 0),
  };
}

export function ConfirmDialogProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<ConfirmRequest | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [remainingDelay, setRemainingDelay] = useState(0);
  const [resolver, setResolver] = useState<((value: boolean) => void) | null>(null);

  const close = useCallback(
    (value: boolean) => {
      if (resolver) resolver(value);
      setResolver(null);
      setRequest(null);
      setInputValue("");
      setRemainingDelay(0);
    },
    [resolver]
  );

  const confirm = useCallback((options: ConfirmOptions) => {
    const normalized = normalizeOptions(options);
    return new Promise<boolean>((resolve) => {
      setRequest(normalized);
      setResolver(() => resolve);
      setInputValue("");
      setRemainingDelay(normalized.delaySeconds);
    });
  }, []);

  const value = useMemo<ConfirmContextValue>(
    () => ({
      confirm,
    }),
    [confirm]
  );

  useEffect(() => {
    if (remainingDelay <= 0) return;
    const timer = window.setTimeout(() => {
      setRemainingDelay((previous) => Math.max(0, previous - 1));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [remainingDelay]);

  const inputMatchesRequirement =
    request?.requireText == null || inputValue.trim() === request.requireText;
  const delayReady = remainingDelay <= 0;

  return (
    <ConfirmDialogContext.Provider value={value}>
      {children}
      {request && (
        <div className="confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
          <div className="confirm-modal panel">
            <h2 id="confirm-title" className="font-semibold mb-2">
              {request.title}
            </h2>
            <p className="text-sm muted mb-3">{request.message}</p>
            {request.requireText && (
              <div className="mb-3">
                <label className="block text-xs text-slate-400 mb-1">
                  {request.inputLabel} ({request.requireText})
                </label>
                <input
                  type="text"
                  value={inputValue}
                  onChange={(event) => setInputValue(event.target.value)}
                  placeholder={request.inputPlaceholder}
                  className="w-full rounded bg-slate-900 px-3 py-2 border border-slate-700"
                />
              </div>
            )}
            <div className="btn-row">
              <button type="button" className="btn btn-neutral" onClick={() => close(false)}>
                {request.cancelLabel}
              </button>
              <button
                type="button"
                className={request.tone === "danger" ? "btn btn-danger" : "btn btn-primary"}
                onClick={() => close(true)}
                disabled={!inputMatchesRequirement || !delayReady}
              >
                {delayReady ? request.confirmLabel : `${request.confirmLabel} (${remainingDelay}s)`}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmDialogContext.Provider>
  );
}

export function useConfirm(): (options: ConfirmOptions) => Promise<boolean> {
  const context = useContext(ConfirmDialogContext);
  if (context) return context.confirm;

  return async (options: ConfirmOptions) => {
    const fallback = normalizeOptions(options);
    return window.confirm(`${fallback.title}\n\n${fallback.message}`);
  };
}
