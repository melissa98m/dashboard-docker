"use client";

import { useAuth } from "../contexts/auth-context";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { loading, authenticated, openAuthPanel } = useAuth();

  if (loading) {
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <p className="text-muted">Chargement…</p>
      </main>
    );
  }

  if (!authenticated) {
    return (
      <main className="page-shell p-4 max-w-4xl mx-auto">
        <div className="panel bg-slate-800/80 rounded-lg p-8 text-center space-y-4">
          <p className="text-lg text-slate-200">
            Pour accéder au dashboard, veuillez vous connecter.
          </p>
          <button
            type="button"
            onClick={openAuthPanel}
            className="btn btn-primary px-6 py-2.5 text-base"
          >
            Se connecter
          </button>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
