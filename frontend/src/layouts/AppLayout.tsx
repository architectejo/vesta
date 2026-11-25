import { useQuery } from "@tanstack/react-query";
import { useMemo, type ReactNode } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { getMyProfile } from "../api/clubs";
import { useAuth } from "../auth/AuthContext";
import {
  ClubBrandingProvider,
  Footer,
  IconNavAnnouncements,
  IconNavArchives,
  IconNavAssembly,
  IconNavBoardDashboard,
  IconNavBoard,
  IconNavChat,
  IconNavContributionsGrid,
  IconNavExpenses,
  IconNavFeed,
  IconNavHome,
  IconNavLocker,
  IconNavMaterial,
  IconNavMedical,
  IconNavMercato,
  IconNavProfile,
  IconNavSessions,
  IconNavSocialAssistance,
  IconNavTreasuryDashboard,
  Sidebar,
  type ClubBranding,
  type SidebarNavGroup,
} from "../design-system";

import { getArchivesAccess } from "../routes/club/archives/archivesAccess";
import { NotificationBellWidget } from "./NotificationBellWidget";

export function AppLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();

  const profileQuery = useQuery({
    queryKey: ["profile", "me"],
    queryFn: getMyProfile,
    staleTime: 60_000,
  });

  const canAccessTreasury = profileQuery.data?.roles.some((role) =>
    ["president", "vice_president", "treasurer", "assistant_treasurer"].includes(role.role),
  ) ?? false;
  // Traitement des demandes d'assistance sociale (CDC 4.5.3, matrice 2.4) :
  // Président et Vice-président seulement. Le Trésorier et son adjoint
  // suivent leurs propres demandes depuis « Mon profil », pas depuis cette
  // page de gestion (fiche `tresorerie-depenses-assistance.md` §2).
  const canProcessAssistance = profileQuery.data?.roles.some((role) =>
    ["president", "vice_president"].includes(role.role),
  ) ?? false;
  // Matériel (fiche `logistique.md` §2, matrice 2.4) : Intendant, Président,
  // Vice-président, Trésorier, Coach seulement — pas une simple lecture
  // ouverte à tout membre actif, contrairement au reste du groupe « Club ».
  const canAccessMaterial = profileQuery.data?.roles.some((role) =>
    ["steward", "president", "vice_president", "treasurer", "coach", "assistant_coach"].includes(role.role),
  ) ?? false;
  // Page « Médical » (medical.md §3) : Médecin, Coach, Président seulement
  // (design-system §3.9 ; matrice 2.4, ligne « Fiches de santé et blessures »).
  const canAccessMedical = profileQuery.data?.roles.some((role) =>
    ["doctor", "coach", "assistant_coach", "president"].includes(role.role),
  ) ?? false;
  // « Archives » (club-archives.md §2) : membres du Bureau seulement. Affichage
  // seulement ; l'API refuse de toute façon (CDC 4.15.1).
  const canAccessArchives = getArchivesAccess(profileQuery.data?.roles).canRead;
  // Tableau de bord du club (fiche `club-tableau-de-bord-bureau.md` §2) : le droit
  // est renvoyé par l'API (`capabilities`), jamais déduit d'un rôle ici.
  const canViewBoardDashboard = profileQuery.data?.capabilities?.can_view_board_dashboard ?? false;
  const navGroups = useMemo<SidebarNavGroup[]>(
    () => [
      {
        items: [
          ...(canViewBoardDashboard
            ? [{ key: "tableau-de-bord", label: "Tableau de bord du club", href: "/tableau-de-bord", icon: <IconNavBoardDashboard aria-hidden="true" className="h-5 w-5" /> }]
            : []),
          { key: "accueil", label: "Accueil", href: "/", icon: <IconNavHome aria-hidden="true" className="h-5 w-5" /> },
          { key: "fil", label: "Fil d'actualité", href: "/fil", icon: <IconNavFeed aria-hidden="true" className="h-5 w-5" /> },
          { key: "profil", label: "Mon profil", href: "/profil", icon: <IconNavProfile aria-hidden="true" className="h-5 w-5" /> },
        ],
      },
      {
        title: "Club",
        items: [
          { key: "comite", label: "Comité et bureau", href: "/club/comite", icon: <IconNavBoard aria-hidden="true" className="h-5 w-5" /> },
          { key: "cartes-joueurs", label: "Cartes des joueurs", href: "/club/joueurs", icon: <IconNavProfile aria-hidden="true" className="h-5 w-5" /> },
          { key: "assemblees", label: "Assemblées générales", href: "/club/assemblees", icon: <IconNavAssembly aria-hidden="true" className="h-5 w-5" /> },
          { key: "communiques", label: "Communiqués", href: "/club/communiques", icon: <IconNavAnnouncements aria-hidden="true" className="h-5 w-5" /> },
          ...(canAccessArchives
            ? [{ key: "archives", label: "Archives", href: "/club/archives", icon: <IconNavArchives aria-hidden="true" className="h-5 w-5" /> }]
            : []),
          { key: "chat", label: "Chat", href: "/club/chat", icon: <IconNavChat aria-hidden="true" className="h-5 w-5" /> },
          // Mercato (fiche `mercato.md` §2) : tous les joueurs du club (au
          // moins « Ma disponibilité » et « Mes offres »).
          { key: "mercato", label: "Mercato", href: "/mercato", icon: <IconNavMercato aria-hidden="true" className="h-5 w-5" /> },
          ...(canAccessMaterial
            ? [{ key: "materiel", label: "Matériel", href: "/materiel", icon: <IconNavMaterial aria-hidden="true" className="h-5 w-5" /> }]
            : []),
          ...(canAccessMedical
            ? [{ key: "medical", label: "Médical", href: "/medical", icon: <IconNavMedical aria-hidden="true" className="h-5 w-5" /> }]
            : []),
        ],
      },
      {
        title: "Sport",
        items: [
          { key: "vestiaire", label: "Vestiaire du jour", href: "/vestiaire", icon: <IconNavLocker aria-hidden="true" className="h-5 w-5" /> },
          // « Entraînements » (sport-statistiques-seance.md B1) : visible de tous
          // les joueurs ; le contenu est filtré par l'API selon le rôle.
          { key: "entrainements", label: "Entraînements", href: "/entrainements", icon: <IconNavSessions aria-hidden="true" className="h-5 w-5" /> },
        ],
      },
      ...(canAccessTreasury
        ? [
            {
              title: "Trésorerie",
              items: [
                { key: "tresorerie", label: "Tableau de bord", href: "/tresorerie", icon: <IconNavTreasuryDashboard aria-hidden="true" className="h-5 w-5" /> },
                { key: "tresorerie-grille", label: "Grille des cotisations", href: "/tresorerie/grille", icon: <IconNavContributionsGrid aria-hidden="true" className="h-5 w-5" /> },
                { key: "tresorerie-depenses", label: "Dépenses", href: "/tresorerie/depenses", icon: <IconNavExpenses aria-hidden="true" className="h-5 w-5" /> },
                ...(canProcessAssistance
                  ? [
                      {
                        key: "tresorerie-assistance",
                        label: "Assistance sociale",
                        href: "/tresorerie/assistance",
                        icon: <IconNavSocialAssistance aria-hidden="true" className="h-5 w-5" />,
                      },
                    ]
                  : []),
              ],
            },
          ]
        : []),
    ],
    [canAccessTreasury, canProcessAssistance, canAccessMaterial, canAccessMedical, canAccessArchives, canViewBoardDashboard],
  );

  const branding: ClubBranding = useMemo(
    () => ({
      name: profileQuery.data?.club.name ?? auth.club?.name ?? "",
      logoUrl: profileQuery.data?.club.logo ?? auth.club?.logo ?? null,
      primaryColor: profileQuery.data?.club.primary_color || auth.club?.primary_color || null,
      secondaryColor: profileQuery.data?.club.secondary_color || auth.club?.secondary_color || null,
    }),
    [profileQuery.data, auth.club],
  );

  const userName = profileQuery.data
    ? `${profileQuery.data.identity.first_name} ${profileQuery.data.identity.last_name}`
    : auth.user
      ? `${auth.user.first_name} ${auth.user.last_name}`
      : "";

  async function handleLogout(): Promise<void> {
    await auth.logout();
    navigate("/connexion");
  }

  return (
    <ClubBrandingProvider branding={branding}>
      <div className="flex min-h-screen flex-col lg:pl-[var(--width-sidebar)]">
        <Sidebar
          groups={navGroups}
          currentPath={location.pathname}
          user={{
            name: userName,
            roleLabel: profileQuery.data?.roles[0]?.label ?? "Joueur",
            photoUrl: profileQuery.data?.identity.photo,
          }}
          profileHref="/profil"
          onNavigate={(href) => navigate(href)}
          onLogout={() => void handleLogout()}
          brandLoading={profileQuery.isLoading}
          topbarRight={<NotificationBellWidget variant="sidebar" />}
        />
        <div className="flex flex-1 flex-col">
          <div className="hidden h-topbar items-center justify-end gap-2 border-b border-border px-4 lg:flex">
            <NotificationBellWidget />
          </div>
          <main className="mx-auto w-full max-w-5xl flex-1 px-3 py-4 sm:px-4">{children}</main>
          <Footer />
        </div>
      </div>
    </ClubBrandingProvider>
  );
}
