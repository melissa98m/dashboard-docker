"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const MAIN_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/commands", label: "Commandes" },
  { href: "/workflows", label: "Workflows" },
  { href: "/alerts", label: "Alertes" },
  { href: "/audit", label: "Audit" },
  { href: "/settings", label: "Parametres" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function MainNav() {
  const pathname = usePathname();

  return (
    <nav className="main-nav" aria-label="Navigation principale">
      {MAIN_LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={isActive(pathname, link.href) ? "main-nav-link is-active" : "main-nav-link"}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
