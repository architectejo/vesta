/**
 * Références réelles du jeu de simulation `fc-malaika` (CDC 9.3, tâche 5.2 ;
 * peuplé par `python manage.py seed_simulation --club fc-malaika`, tâche
 * 5.1). Ces identifiants ont été relevés par une requête ORM en lecture
 * seule dans la base de dev réelle avant d'écrire ce parcours — jamais
 * inventés — et peuvent nécessiter une mise à jour si `seed_simulation` est
 * rejoué avec un jeu de données différent.
 */
export const CLUB_SLUG = "fc-malaika";

export const ACCOUNTS = {
  president: "jonathan777t@gmail.com",
  treasurer: "adolphe.ciruzi@discoveryclub.cd",
  coach: "emmanuel.isikisiki@discoveryclub.cd",
  doctor: "jules.baganda@discoveryclub.cd",
  captain: "alain.bisimwa@discoveryclub.cd",
  /** Compte synthétique explicitement nommé comme tel (voir seed_simulation.py) : seul moyen légitime de démontrer une action exigeant un code PIN sans toucher au PIN d'un compte réel. */
  demoAssistantTreasurer: "demo.tresorier.adjoint@simulation.vesta.local",
  superuser: "architecte@vesta.hub",
} as const;

export const DEMO_ASSISTANT_PIN = "4815";

export const DEBTOR = {
  membershipId: 86,
  email: "willy.mburugu@discoveryclub.cd",
  // Dette garantie par seed_simulation : type "Cotisation exceptionnelle
  // (tournoi régional)", 15/mois, août + septembre 2026 jamais payés = 30.
  debtAmount: "30",
};

export const LATE_ARRIVAL_CANDIDATE = {
  membershipId: 13,
  email: "faustin.kasusula@discoveryclub.cd",
};

export const SPORTS_DIRECTOR_CANDIDATE = {
  membershipId: 15,
  email: "popaul.kizungu@discoveryclub.cd",
};

/** Match du 13/09/2026, confirmé "propre" (aucune composition stockée) avant l'écriture de ce parcours — à la différence du match 16, qui porte une composition figée résiduelle d'une exécution antérieure de `seed_simulation` (voir compte rendu : point ouvert, hygiène des données de démo). */
export const CLEAN_MATCH_ID = 14;

/** Séance du jour (2026-09-30 == date réelle du poste de dev) : fenêtre de verrouillage des évaluations (48 h après le début réel) encore ouverte. */
export const TODAY_SESSION_ID = 17;

export const ASSEMBLY_ID = 1;

export const OTHER_CLUB_SLUG = "club-test-1";
