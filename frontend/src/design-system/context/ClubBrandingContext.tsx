import { createContext, useContext, type ReactNode } from "react";

/**
 * Identité visuelle du club connecté (docs/lot0/design-system.md §2.4, 3.9).
 * Toujours fournie par l'API (identité du club) : aucune valeur par défaut
 * propre à un club réel n'est écrite ici. Le composant appelant (au Lot 1.9,
 * une fois l'API des comptes disponible) est responsable de peupler ce
 * contexte à partir de la réponse de l'API.
 */
export interface ClubBranding {
  /** Nom du club, tel qu'enregistré par le club. */
  name: string;
  /** URL de l'image du logo, ou `null` si le club n'en a pas fourni. */
  logoUrl: string | null;
  /** Couleur principale extraite du logo (hex), validée par le Président. */
  primaryColor: string | null;
  /** Couleur secondaire extraite du logo (hex), validée par le Président. */
  secondaryColor: string | null;
}

const ClubBrandingContext = createContext<ClubBranding | null>(null);

export function ClubBrandingProvider({
  branding,
  children,
}: {
  branding: ClubBranding;
  children: ReactNode;
}) {
  return (
    <ClubBrandingContext.Provider value={branding}>{children}</ClubBrandingContext.Provider>
  );
}

/**
 * Renvoie l'identité du club connecté. En dehors d'un `ClubBrandingProvider`
 * (ex. espace Superuser, écran de connexion avant sélection du club), renvoie
 * `null` : les composants doivent alors se rabattre sur un état neutre
 * générique (carré aux initiales, pas de couleur d'accent).
 */
export function useClubBranding(): ClubBranding | null {
  return useContext(ClubBrandingContext);
}
