/**
 * Petits utilitaires de date/heure partagés par les écrans du Lot 3.
 * Simplification documentée au compte rendu : combine une date et une
 * heure saisies comme si elles étaient dans le fuseau du navigateur (en
 * pratique celui du club, l'équipe opérant sur place) — aucun fuseau de
 * club n'est chargé par ces écrans, à la différence de
 * `routes/treasury/money.ts` qui en a besoin pour la Caisse Terrain
 * Express.
 */

export function combineDateTimeToIso(dateStr: string, timeStr: string): string {
  const normalizedTime = timeStr.length === 5 ? `${timeStr}:00` : timeStr;
  return new Date(`${dateStr}T${normalizedTime}`).toISOString();
}

export function formatTime(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function nowTimeHHMM(): string {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}
