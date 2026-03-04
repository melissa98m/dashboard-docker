"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Application error:", error);
  }, [error]);

  return (
    <main className="page-shell p-4 max-w-4xl mx-auto">
      <div className="panel bg-red-950/30 border border-red-800 rounded-lg p-6">
        <h1 className="text-xl font-bold text-red-300 mb-2">
          Erreur de l&apos;application
        </h1>
        <p className="text-slate-400 text-sm mb-4">{error.message}</p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => reset()}
            className="btn btn-primary px-4 py-2"
          >
            Réessayer
          </button>
          <Link href="/" className="btn btn-neutral px-4 py-2">
            Accueil
          </Link>
        </div>
      </div>
    </main>
  );
}
