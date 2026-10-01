/**
 * TEMPORAIRE : à remplacer par des capacités renvoyées par l'API.
 *
 * Ces deux ensembles recopient la matrice de permissions du backend
 * (cahier des charges 2.4 et 4.4.1). Ils contredisent la règle « aucune règle
 * métier dans l'interface » et ne doivent exister qu'ici, le temps que l'API
 * expose les capacités de l'utilisateur (lecture et écriture de la
 * trésorerie). Le comportement actuel est conservé à l'identique.
 */
const TREASURY_WRITE_ROLES: ReadonlySet<string> = new Set(["president", "treasurer"]);
const TREASURY_READ_ROLES: ReadonlySet<string> = new Set([
  "president",
  "vice_president",
  "treasurer",
  "assistant_treasurer",
]);

export interface TreasuryAccess {
  canRead: boolean;
  canWrite: boolean;
}

export function getTreasuryAccess(roles: ReadonlyArray<{ role: string }> | undefined): TreasuryAccess {
  const keys = (roles ?? []).map((entry) => entry.role);
  return {
    canRead: keys.some((role) => TREASURY_READ_ROLES.has(role)),
    canWrite: keys.some((role) => TREASURY_WRITE_ROLES.has(role)),
  };
}
