import type { Metadata } from "next";
import "./globals.css";
import Breadcrumbs from "./components/breadcrumbs";
import AuthAccessPanel from "./components/auth-access-panel";
import { ConfirmDialogProvider } from "./components/confirm-dialog";
import MainNav from "./components/main-nav";
import { NotificationsProvider } from "./components/notifications";
import ThemeToggle from "./components/theme-toggle";

export const metadata: Metadata = {
  title: "Dashboard Docker",
  description: "Monitoring et gestion des conteneurs Docker",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr">
      <body>
        <NotificationsProvider>
          <ConfirmDialogProvider>
            <div className="app-shell">
              <header className="topbar">
                <div className="topbar-main">
                  <p className="topbar-title">Docker Dashboard</p>
                  <MainNav />
                </div>
                <div className="topbar-actions">
                  <AuthAccessPanel />
                  <ThemeToggle />
                </div>
              </header>
              <div className="app-content">
                <div className="page-shell">
                  <Breadcrumbs />
                </div>
                {children}
              </div>
            </div>
          </ConfirmDialogProvider>
        </NotificationsProvider>
      </body>
    </html>
  );
}
