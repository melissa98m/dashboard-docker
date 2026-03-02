import Link from "next/link";
export default function AlertsPage() {
  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">Alertes</h1>
        <p className="muted text-sm">Chaque fonctionnalite est sur une page dediee.</p>
      </div>

      <section className="panel">
        <div className="grid gap-3">
          <Link href="/alerts/rules" className="entity-card">
            <p className="font-semibold">Regles d&apos;alertes</p>
            <p className="text-sm muted">Creer, lister et supprimer les regles actives.</p>
          </Link>
          <Link href="/alerts/history" className="entity-card">
            <p className="font-semibold">Historique des declenchements</p>
            <p className="text-sm muted">Filtrer les alertes recentes et relancer un conteneur.</p>
          </Link>
        </div>
      </section>
    </main>
  );
}
