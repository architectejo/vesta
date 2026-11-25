import type { BoardPeriodQuery, Rate } from "../../../api/clubBoardDashboard";
import { formatDateFr, formatNumber } from "../../treasury/money";

export { formatAmount, formatDateFr, formatNumber } from "../../treasury/money";

/** Taux servi par l'API (« 74.00 ») -> « 74 % » ; absent -> « — ». Jamais recalculé ici. */
export function rateText(rate: Rate | undefined): string {
  if (rate === null || rate === undefined) return "—";
  return `${formatNumber(rate)} %`;
}

export function rateNumber(rate: Rate | undefined): number | null {
  if (rate === null || rate === undefined) return null;
  const value = Number(rate);
  return Number.isNaN(value) ? null : value;
}

/** Montant ou note en chaîne -> nombre pour un graphique (affichage seulement). */
export function toChartNumber(raw: string | null | undefined): number | null {
  if (raw === null || raw === undefined) return null;
  const value = Number(raw);
  return Number.isNaN(value) ? null : value;
}

export function plural(count: number, one: string, many: string): string {
  return `${formatNumber(count)} ${count > 1 ? many : one}`;
}

/** « 2026-11 » -> « nov. 26 » (deux lignes dans un graphique, jamais tronqué). */
export function shortMonth(month: string): string {
  const [yearText, monthText] = month.split("-");
  const date = new Date(Date.UTC(Number(yearText), Number(monthText) - 1, 1));
  if (Number.isNaN(date.getTime())) return month;
  const name = date.toLocaleDateString("fr-FR", { month: "short", timeZone: "UTC" });
  return `${name} ${String(yearText).slice(2)}`;
}

/** « 2026-11-08 » -> « 8 nov. ». */
export function shortDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" }).format(date);
}

export function dateLabel(iso: string | null | undefined): string {
  return iso ? formatDateFr(iso) : "";
}

/** Clé de cache stable d'une période. */
export function periodKey(period: BoardPeriodQuery | null): string {
  if (!period) return "current";
  return period.mode === "month" ? `month:${period.month}` : `season:${period.seasonId ?? "current"}`;
}
