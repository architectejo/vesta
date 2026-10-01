/** Formats de date partagés par les écrans logistique (fiche `logistique.md`). */

/** « 12/03/2026 » à partir d'une date « YYYY-MM-DD ». */
export function formatDateFr(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

/** « 12/03/2026 14:05 » à partir d'un horodatage ISO complet. */
export function formatDateTimeFr(isoDateTime: string): string {
  const date = new Date(isoDateTime);
  if (Number.isNaN(date.getTime())) return isoDateTime;
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/** Date du jour au format « YYYY-MM-DD » (fuseau local du navigateur). */
export function todayIsoDate(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}
