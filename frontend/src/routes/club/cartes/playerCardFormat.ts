import type { StatusKey } from "../../../design-system";
import type { PlayerTradingCardStats } from "../../../design-system";
import type {
  PlayerCardAvailability,
  PlayerFitnessStatus,
  PlayerSeasonStats,
} from "../../../api/playerCards";

/** « 6.8 » -> « 6,8 » ; `null` -> « — » (pas encore de donnée, jamais « 0 »). */
export function formatRating(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return value.replace(".", ",");
}

export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value} %`;
}

/** « 8 nov. 2026 » à partir d'une date « AAAA-MM-JJ ». */
export function formatShortDate(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", year: "numeric" }).format(date);
}

/** Adapte les statistiques de l'API (note en chaîne) à la carte du design system. */
export function toCardStats(stats: PlayerSeasonStats): PlayerTradingCardStats {
  const rating = stats.average_rating === null ? null : Number(stats.average_rating);
  return {
    matchesPlayed: stats.matches_played,
    goals: stats.goals,
    assists: stats.assists,
    yellowCards: stats.yellow_cards,
    redCards: stats.red_cards,
    attendanceRate: stats.attendance_rate,
    averageRating: rating !== null && Number.isFinite(rating) ? rating : null,
  };
}

export function plural(count: number, one: string, many: string): string {
  return `${count} ${count > 1 ? many : one}`;
}

/**
 * Pastille de disponibilité (staff seulement). Une dette n'est jamais nommée :
 * l'API sert un libellé neutre (« Non éligible. » pour le Coach), affiché tel
 * quel. Le motif (suspension,
 * inaptitude) n'apparaît que s'il est servi.
 */
export function availabilityBadge(availability: PlayerCardAvailability): {
  status: StatusKey;
  detail?: string;
  label?: string;
} {
  switch (availability.family) {
    case "suspension":
      return { status: "suspended", detail: stripPrefix(availability.label, /^Suspendu\s*[:·]?\s*/) };
    case "unfit":
      return { status: "unfit", detail: stripPrefix(availability.label, /^Inapte\s*[:·]?\s*/) };
    case "pending":
      return { status: "pending" };
    default:
      // Libellé de l'API tel quel (ex. « Non éligible. » pour le Coach,
      // CDC 10.3 n° 188) ; couleur grise de la clé ; repli « Indisponible »
      // seulement si l'API n'a servi aucun libellé.
      return { status: "medical_unavailable", label: availability.label.trim() || undefined };
  }
}

function stripPrefix(label: string, pattern: RegExp): string | undefined {
  const rest = label.replace(pattern, "").trim();
  return rest === "" ? undefined : rest;
}

export const FITNESS_STATUS_KEY: Record<PlayerFitnessStatus, StatusKey> = {
  fit: "fit",
  fit_with_restriction: "fit_restricted",
  unfit: "unfit",
};
