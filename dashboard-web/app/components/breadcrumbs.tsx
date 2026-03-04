"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LABELS: Record<string, string> = {
  alerts: "Alertes",
  audit: "Audit",
  commands: "Commandes",
  containers: "Conteneurs",
  history: "Historique",
  images: "Images",
  live: "Temps reel",
  rules: "Règles",
  settings: "Paramètres",
  logs: "Logs",
  environment: "Environnement",
  catalog: "Catalogue",
  volumes: "Volumes",
  workflows: "Workflows",
};

function toLabel(segment: string): string {
  if (LABELS[segment]) return LABELS[segment];
  if (segment.length <= 14) return segment;
  return `${segment.slice(0, 12)}...`;
}

export default function Breadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  const items = [{ href: "/", label: "Accueil" }].concat(
    segments.map((segment, index) => ({
      href: `/${segments.slice(0, index + 1).join("/")}`,
      label: toLabel(segment),
    }))
  );

  return (
    <nav className="breadcrumbs" aria-label="Fil d'ariane">
      <ol>
        {items.map((item, index) => {
          const isLast = index === items.length - 1;
          return (
            <li
              key={item.href}
              className={
                index > 1 && index < items.length - 1
                  ? "crumb-hide-mobile"
                  : undefined
              }
            >
              {isLast ? (
                <span aria-current="page">{item.label}</span>
              ) : (
                <Link href={item.href}>{item.label}</Link>
              )}
              {!isLast && <span className="crumb-separator">/</span>}
            </li>
          );
        })}
        {items.length > 3 && <li className="crumb-mobile-ellipsis">...</li>}
      </ol>
    </nav>
  );
}
