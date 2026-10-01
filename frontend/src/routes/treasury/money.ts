/**
 * Nombre seul, sans devise (docs/lot0/design-system.md §2.6 : cellules de la
 * grille des cotisations, trop étroites pour répéter la devise à chaque
 * cellule — elle est rappelée une fois dans la légende). Décimales masquées
 * si nulles. Ne recalcule jamais un montant : `raw` vient toujours d'une
 * réponse API.
 */
export function formatNumber(raw: string | number): string {
  const value = typeof raw === "string" ? Number(raw) : raw;
  if (Number.isNaN(value)) return String(raw);
  const hasCents = Math.abs(value % 1) > 0.001;
  return new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: hasCents ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * Formats d'affichage des montants (docs/lot0/design-system.md §4) : devise
 * du club venant de l'API, décimales masquées si nulles. Ne recalcule
 * jamais un montant : `raw` vient toujours d'une réponse API.
 */
export function formatAmount(raw: string | number, currency: string): string {
  if (typeof raw === "string" && Number.isNaN(Number(raw))) return `${raw} ${currency}`;
  return `${formatNumber(raw)} ${currency}`;
}

/** « 12/03/2026 » à partir d'une date « YYYY-MM-DD ». */
export function formatDateFr(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

/** « mars 2026 » à partir d'une date « YYYY-MM-DD ». */
export function formatMonthYear(period: string): string {
  const date = new Date(`${period}T00:00:00`);
  if (Number.isNaN(date.getTime())) return period;
  return new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" }).format(date);
}

/** Normalise la virgule décimale saisie en point avant l'envoi à l'API. */
export function toApiAmount(value: string): string {
  return value.replace(/,/g, ".");
}

/** Date du jour au format « YYYY-MM-DD » (fuseau local du navigateur). */
export function todayIsoDate(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}
