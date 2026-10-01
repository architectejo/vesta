import type { CSSProperties } from "react";
import { useMediaQuery } from "../../hooks/useMediaQuery";

/**
 * Plafonne la largeur — donc la hauteur, via le ratio d'aspect CSS du
 * terrain portrait (`aspect-[68/105]`, `PitchBoard.tsx`) — d'un terrain
 * affiché sur une page (Séance §3.2, Vestiaire du jour §3 point 3), pour
 * qu'il tienne sans défilement vertical sur un écran d'ordinateur standard
 * (remarques.md, demande explicite du client du 30/09/2026 : « en hauteur
 * les terrains sont très longs, ils doivent tenir sur l'écran de
 * l'ordinateur, pas besoin de scroller »).
 *
 * Même technique que `PlanDetailModal.tsx` : `PitchBoard` dérive toujours
 * sa hauteur de sa largeur (jamais l'inverse), donc on borne la largeur à
 * partir d'un budget de hauteur plutôt que l'inverse.
 *
 * Sous 768 px (point de rupture `md:` de la grille à deux colonnes), le
 * terrain garde sa pleine largeur : un seul terrain à la fois y est déjà
 * affiché pleine largeur, le défilement vertical normal du mobile n'est
 * pas ce que le client a signalé.
 */
export function useTeamsPitchWidthStyle(): CSSProperties | undefined {
  const isDesktop = useMediaQuery("(min-width: 768px)");
  if (!isDesktop) return undefined;
  // Budget généreux pour un écran d'ordinateur standard (768-900 px de
  // hauteur utile une fois l'en-tête, les bandeaux et les autres cartes de
  // la page déduits), plafonné en valeur absolue pour ne pas grandir sans
  // limite sur un très grand écran.
  const heightBudget = "min(56vh, 520px)";
  return { maxWidth: `calc(${heightBudget} * 68 / 105)`, marginInline: "auto" };
}
