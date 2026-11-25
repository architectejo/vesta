import type { ReactNode } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { ClubBrandingProvider, Footer, Sidebar, type SidebarNavGroup } from "../../design-system";
import { NotificationBellWidget } from "../../layouts/NotificationBellWidget";
import { SupportSessionBanner } from "./SupportSessionBanner";

const NAV_GROUPS: SidebarNavGroup[] = [
  {
    items: [
      { key: "dashboard", label: "Tableau de bord", href: "/admin" },
      { key: "clubs", label: "Clubs et licences", href: "/admin/clubs" },
      { key: "users", label: "Utilisateurs", href: "/admin/utilisateurs" },
      { key: "journal", label: "Journal d'activité", href: "/admin/journal" },
      { key: "parametres", label: "Paramètres", href: "/admin/parametres" },
    ],
  },
];

/**
 * Espace Superuser (docs/ecrans/superuser-espace.md §2) : pas de fiche
 * joueur, pas de marque blanche. « Vesta — Administration » réutilise
 * `Sidebar`/`ClubBrandingContext` avec un logo neutre (aucune couleur
 * Classic n'est appliquée, `primaryColor: null`).
 */
export function AdminLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();

  async function handleLogout(): Promise<void> {
    await auth.logout();
    navigate("/connexion");
  }

  return (
    <ClubBrandingProvider
      branding={{ name: "Vesta — Administration", logoUrl: null, primaryColor: null, secondaryColor: null }}
    >
      <div className="flex min-h-screen flex-col lg:pl-[var(--width-sidebar)]">
        <Sidebar
          groups={NAV_GROUPS}
          currentPath={location.pathname}
          user={{
            name: auth.user ? `${auth.user.first_name} ${auth.user.last_name}` : "",
            roleLabel: "Superuser",
          }}
          profileHref="/admin"
          onNavigate={(href) => navigate(href)}
          onLogout={() => void handleLogout()}
          topbarRight={<NotificationBellWidget variant="sidebar" />}
        />
        <div className="flex flex-1 flex-col">
          <div className="hidden h-topbar items-center justify-end gap-2 border-b border-border px-4 lg:flex">
            <NotificationBellWidget />
          </div>
          <SupportSessionBanner />
          <main className="mx-auto w-full max-w-5xl flex-1 px-3 py-4 sm:px-4">{children}</main>
          <Footer />
        </div>
      </div>
    </ClubBrandingProvider>
  );
}
