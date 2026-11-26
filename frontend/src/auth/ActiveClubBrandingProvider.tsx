import { useQuery } from "@tanstack/react-query";
import { useMemo, type ReactNode } from "react";
import { getMyProfile } from "../api/clubs";
import { ClubBrandingProvider, type ClubBranding } from "../design-system";
import { useAuth } from "./AuthContext";

/**
 * Aucune session active, ou espace Superuser : jamais de marque blanche
 * (CLAUDE.md §2 n°18/19 ; docs/ecrans/superuser-espace.md §2). `ThemeProvider`
 * retombe alors sur les neutres du thème Clair.
 */
const NEUTRAL_BRANDING: ClubBranding = {
  name: "",
  logoUrl: null,
  primaryColor: null,
  secondaryColor: null,
};

/**
 * Résout la marque (branding) du club actif de la session en cours et la
 * rend disponible à tout l'arbre, **`ThemeProvider` compris** (design-system,
 * §2.4, §7.2) : les variables CSS globales du thème Classic
 * (`--color-primary`, `--color-sidebar-bg`…) doivent refléter les vraies
 * couleurs du club, pas seulement les composants qui appellent
 * `useClubBranding()` localement (Sidebar, Footer, PlayerTradingCard).
 *
 * Placé dans `main.tsx` **entre `AuthProvider` et `ThemeProvider`** : avant ce
 * correctif, `ThemeProvider` était à la racine de l'arbre et ne voyait donc
 * jamais le `ClubBrandingProvider` posé par `AppLayout`, lui-même un
 * descendant — `useContext` ne remonte jamais un arbre React. Résultat : les
 * couleurs Classic n'étaient jamais appliquées en usage réel, quel que soit
 * le club connecté.
 *
 * Même formule de repli que l'ancienne implémentation locale d'`AppLayout`
 * (profil API en priorité, identité de connexion en repli le temps du premier
 * chargement) : ne change aucune règle métier, seulement sa portée.
 */
export function ActiveClubBrandingProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const isClubMember = auth.status === "authenticated" && !auth.user?.is_superuser;
  // Mot de passe provisoire (ex. Président juste après « Créer un club ») :
  // aucune donnée du club n'est demandée avant le changement obligatoire
  // (comptes-connexion.md §4.2) — l'API répondrait 403. L'instantané de
  // connexion sert de marque blanche en attendant (série 6).
  const mustChangePassword = Boolean(auth.user?.must_change_password);

  const profileQuery = useQuery({
    queryKey: ["profile", "me"],
    queryFn: getMyProfile,
    staleTime: 60_000,
    enabled: isClubMember && !mustChangePassword,
  });

  const branding = useMemo<ClubBranding>(() => {
    if (!isClubMember) return NEUTRAL_BRANDING;
    return {
      name: profileQuery.data?.club.name ?? auth.club?.name ?? "",
      logoUrl: profileQuery.data?.club.logo ?? auth.club?.logo ?? null,
      primaryColor: profileQuery.data?.club.primary_color || auth.club?.primary_color || null,
      secondaryColor: profileQuery.data?.club.secondary_color || auth.club?.secondary_color || null,
    };
  }, [isClubMember, profileQuery.data, auth.club]);

  return <ClubBrandingProvider branding={branding}>{children}</ClubBrandingProvider>;
}
