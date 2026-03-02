import Link from "next/link";

export default function CommandsPage() {
  return (
    <main className="page-shell p-4 max-w-4xl mx-auto space-y-4">
      <div className="page-header">
        <h1 className="page-title text-2xl font-bold">Centre de commandes</h1>
        <p className="muted text-sm">Une fonctionnalite par page pour une UX plus claire.</p>
      </div>

      <section className="panel">
        <div className="grid gap-3">
          <Link href="/commands/catalog" className="entity-card">
            <p className="font-semibold">Catalogue de commandes</p>
            <p className="text-sm muted">Creer, scanner et executer des commandes allowlistees.</p>
          </Link>
          <Link href="/commands/live" className="entity-card">
            <p className="font-semibold">Terminal live</p>
            <p className="text-sm muted">Suivre les sorties stdout/stderr en direct.</p>
          </Link>
          <Link href="/commands/history" className="entity-card">
            <p className="font-semibold">Historique</p>
            <p className="text-sm muted">Consulter les executions passees et leur statut.</p>
          </Link>
        </div>
      </section>
    </main>
  );
}
