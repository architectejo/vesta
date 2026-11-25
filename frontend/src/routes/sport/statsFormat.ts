/**
 * Mise en forme des statistiques de séance. Aucune règle métier : les valeurs
 * (taux, notes, écarts) sont calculées par l'API ; on ne fait qu'afficher.
 */

/** « 72 % » ; `null` (séance sans pointage) -> « — », jamais « 0 % ». */
export function formatRate(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? "—" : `${rate} %`;
}

/** « 6.8 » (chaîne décimale de l'API) -> « 6,8 ». `null` -> « — ». */
export function formatNote(value: string | null | undefined): string {
  return value === null || value === undefined ? "—" : value.replace(".", ",");
}

/** Écart signé : « +6 », « −4 », « 0 » (vrai signe moins). */
export function formatSignedInt(value: number): string {
  if (value > 0) return `+${value}`;
  if (value < 0) return `−${Math.abs(value)}`;
  return "0";
}

/** Écart décimal signé servi en chaîne (« 0.4 » -> « +0,4 »). */
export function formatSignedNote(value: string): string {
  const text = value.replace(".", ",");
  if (text.startsWith("-")) return `−${text.slice(1)}`;
  if (Number(value) > 0) return `+${text}`;
  return text;
}

/** « 2026-11-08 » -> « 08/11 » (axe des courbes). */
export function shortDateLabel(isoDate: string): string {
  return `${isoDate.slice(8, 10)}/${isoDate.slice(5, 7)}`;
}

/** « 2026-11-08 » -> « dim. 8 nov. ». */
export function formatSessionDate(isoDate: string): string {
  return new Date(`${isoDate}T12:00:00`).toLocaleDateString("fr-FR", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

/** « 2026-11-08 » -> « dimanche 8 novembre 2026 ». */
export function formatLongDate(isoDate: string): string {
  return new Date(`${isoDate}T12:00:00`).toLocaleDateString("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function formatDayMonth(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "long" });
}

export function plural(count: number, one: string, many: string): string {
  return count > 1 ? many : one;
}
