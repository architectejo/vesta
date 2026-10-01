import { useQuery } from "@tanstack/react-query";
import { useMemo, type ReactNode } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { getMyProfile } from "../api/clubs";
import { useAuth } from "../auth/AuthContext";
import {
  ClubBrandingProvider,
  Footer,
  Sidebar,
  type ClubBranding,
  type SidebarNavGroup,
} from "../design-system";

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
    ["steward", "president", "vice_president", "treasurer", "coach"].includes(role.role),
  ) ?? false;
  // Page « Médical » (medical.md §3) : Médecin, Coach, Président seulement
  // (design-system §3.9 ; matrice 2.4, ligne « Fiches de santé et blessures »).
  const canAccessMedical = profileQuery.data?.roles.some((role) =>
    ["doctor", "coach", "president"].includes(role.role),
  ) ?? false;
  const navGroups = useMemo<SidebarNavGroup[]>(
    () => [
      {
        items: [
          { key: "accueil", label: "Accueil", href: "/" },
          { key: "fil", label: "Fil d'actualité", href: "/fil" },
          { key: "profil", label: "Mon profil", href: "/profil" },
        ],
      },
      {
        title: "Club",
        items: [
          { key: "comite", label: "Comité et bureau", href: "/club/comite" },
          { key: "assemblees", label: "Assemblées générales", href: "/club/assemblees" },
          { key: "communiques", label: "Communiqués", href: "/club/communiques" },
          { key: "chat", label: "Chat", href: "/club/chat" },
          // Mercato (fiche `mercato.md` §2) : tous les joueurs du club (au
          // moins « Ma disponibilité » et « Mes offres »).
          { key: "mercato", label: "Mercato", href: "/mercato" },
          ...(canAccessMaterial ? [{ key: "materiel", label: "Matériel", href: "/materiel" }] : []),
          ...(canAccessMedical ? [{ key: "medical", label: "Médical", href: "/medical" }] : []),
        ],
      },
      {
        title: "Sport",
        items: [
          { key: "vestiaire", label: "Vestiaire du jour", href: "/vestiaire" },
          { key: "plans", label: "Plan tactique", href: "/plans" },
        ],
      },
      ...(canAccessTreasury
        ? [
            {
              title: "Trésorerie",
              items: [
                { key: "tresorerie", label: "Tableau de bord", href: "/tresorerie" },
                { key: "tresorerie-grille", label: "Grille des cotisations", href: "/tresorerie/grille" },
                { key: "tresorerie-depenses", label: "Dépenses", href: "/tresorerie/depenses" },
                ...(canProcessAssistance
                  ? [{ key: "tresorerie-assistance", label: "Assistance sociale", href: "/tresorerie/assistance" }]
                  : []),
              ],
            },
          ]
        : []),
    ],
    [canAccessTreasury, canProcessAssistance, canAccessMaterial, canAccessMedical],
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
        />
        <div className="flex flex-1 flex-col">
          <main className="mx-auto w-full max-w-5xl flex-1 px-3 py-4 sm:px-4">{children}</main>
          <Footer />
        </div>
      </div>
    </ClubBrandingProvider>
  );
}
