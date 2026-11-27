/**
 * Références de la base locale de DÉMONSTRATION de dev-b (club fictif
 * « Club Démo », slug `club-demo`, comptes `@demo.local`). Données
 * entièrement fictives. Relevées en lecture seule par l'API (aucune requête
 * ORM, aucun `shell`) avant l'écriture de la série 5 (`10-serie5.spec.ts`).
 * À mettre à jour si la base de démonstration est recréée.
 */
export const DEMO_CLUB_SLUG = "club-demo";

export const DEMO = {
  president: "president@demo.local",
  vicePresident: "vp@demo.local",
  treasurer: "tresorier@demo.local",
  coach: "coach@demo.local",
  /** joueur01 porte le rôle Médecin. */
  doctor: "joueur01@demo.local",
  /** joueur02 porte le rôle Capitaine. */
  captain: "joueur02@demo.local",
  /** Joueur sans autre rôle (non pointé à la séance du jour au départ). */
  player: "joueur05@demo.local",
} as const;

/** Séance du jour (recréée chaque jour par la préparation de la base de démonstration). */
export const TODAY_SESSION_ID = 7;

/**
 * Joueurs que l'API déclare indisponibles (`is_unavailable`, sans motif) :
 * dette, suspension ou inaptitude. Victor Echant et William Placebo sont
 * inaptes (carte « Aptitude » du tableau de bord).
 */
export const UNAVAILABLE_PLAYERS = [
  "Victor Echant",
  "William Placebo",
  "Didier Exempled",
  "Éric Imaginée",
  "Aimé Leurre",
] as const;

/** Joueurs disponibles, non pointés au départ de la série 5. */
export const AVAILABLE_UNMARKED_PLAYERS = [
  "Thierry Anonyme",
  "Zacharie Chimere",
  "Marc Factice",
  "Quentin Figurant",
  "Olivier Lambdao",
  "Yves Mirage",
  "Rémi Nomfictif",
  "Serge Pseudo",
  "Pascal Quidamp",
  "Noël Sansnom",
  "Ulrich Zedu",
] as const;

export const PUBLISHED_PLAN_NAME = "Démo — 4-3-3 de base";
export const DRAFT_PLAN_NAME = "Démo — brouillon 4-4-2";

export const PERFORMANCE_TESTS = ["Sprint 30 m", "Navette 5 × 10 m", "Test de Cooper (12 min)", "Jongles en 1 minute"] as const;

const CLUB_TIME_ZONE = "Africa/Kinshasa";

/** Date du jour dans le fuseau du club, format court des listes : « ven. 27 nov. ». */
export function todayShortLabel(): string {
  return new Intl.DateTimeFormat("fr-FR", { timeZone: CLUB_TIME_ZONE, weekday: "short", day: "numeric", month: "short" }).format(new Date());
}

/** Date du jour dans le fuseau du club, format long : « vendredi 27 novembre ». */
export function todayLongLabel(): string {
  return new Intl.DateTimeFormat("fr-FR", { timeZone: CLUB_TIME_ZONE, weekday: "long", day: "numeric", month: "long" }).format(new Date());
}

export function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
