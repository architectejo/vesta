/**
 * Formatage de date/heure du module Médical (docs/lot0/design-system.md
 * §4 : « dim. 12 oct. 2026 »). Réplique exactement
 * `apps.medical.services.format_date_fr` côté API — utilisé ici pour des
 * dates qui n'arrivent PAS déjà formatées par l'API (ex. `reported_at`
 * d'une blessure, entrée de suivi) ; quand l'API fournit un libellé déjà
 * composé (ex. `fitness_return_date_label`), on l'affiche tel quel sans
 * jamais le recomposer (medical.md §2.4).
 */

const WEEKDAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."];
const MONTHS = [
  "janv.", "févr.", "mars", "avr.", "mai", "juin",
  "juil.", "août", "sept.", "oct.", "nov.", "déc.",
];

/** « dim. 12 oct. 2026 » à partir d'une date « YYYY-MM-DD » ou d'un ISO datetime. */
export function formatDateFrLong(value: string): string {
  const isoDatePart = value.length >= 10 ? value.slice(0, 10) : value;
  const date = new Date(`${isoDatePart}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  const weekday = WEEKDAYS[(date.getDay() + 6) % 7];
  const month = MONTHS[date.getMonth()];
  return `${weekday} ${date.getDate()} ${month} ${date.getFullYear()}`;
}

/** « 14:30 » à partir d'un ISO datetime. */
export function formatTimeFr(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

/** Date du jour au format « YYYY-MM-DD » (fuseau local du navigateur — même
 * simplification documentée que `routes/sport/sportTime.ts`). */
export function todayIsoDate(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}

/** « 08:00 » actuel (fuseau du navigateur). */
export function nowTimeHHMM(): string {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}
