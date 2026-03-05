import type { Metadata, Viewport } from "next";
import "./globals.css";
import Breadcrumbs from "./components/breadcrumbs";
import AuthAccessPanel from "./components/auth-access-panel";
import AuthGate from "./components/auth-gate";
import { ConfirmDialogProvider } from "./components/confirm-dialog";
import MainNav from "./components/main-nav";
import { NotificationsProvider } from "./components/notifications";
import ThemeToggle from "./components/theme-toggle";
import { AuthProvider } from "./contexts/auth-context";

export const metadata: Metadata = {
  title: "Dashboard Docker",
  description: "Monitoring et gestion des conteneurs Docker sur Raspberry Pi",
  manifest: "/manifest.json",
  appleWebApp: { capable: true, title: "Docker Dashboard" },
  icons: {
    icon: "/icon-192.png",
    apple: "/icon-192.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#0f172a",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <NotificationsProvider>
          <ConfirmDialogProvider>
            <AuthProvider>
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
                  <AuthGate>{children}</AuthGate>
                </div>
              </div>
            </AuthProvider>
          </ConfirmDialogProvider>
        </NotificationsProvider>
      </body>
    </html>
  );
}
