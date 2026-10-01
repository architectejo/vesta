import type { StatusKey } from "../../design-system";
import type { FitnessStatus, InjuryListItem } from "../../api/medical";
import { formatDateFrLong } from "./medicalFormat";

/** `StatusBadge` d'aptitude (medical.md §2.1, §3.2, §4.2, §4.4). */
export function fitnessStatusKey(status: FitnessStatus): StatusKey {
  if (status === "unfit") return "unfit";
  if (status === "fit_with_restriction") return "fit_restricted";
  return "fit";
}

/** `StatusBadge` d'une blessure (medical.md §3.1, §3.4, §4.3). */
export function injuryStatusKey(item: { status: "open" | "resolved"; doctor_completed: boolean }): StatusKey {
  if (item.status === "resolved") return "medical_injury_resolved";
  if (!item.doctor_completed) return "medical_injury_to_complete";
  return "medical_injury_open";
}

export function injuryStatusLabel(item: { status: "open" | "resolved"; doctor_completed: boolean }): string {
  if (item.status === "resolved") return "Retour déclaré";
  if (!item.doctor_completed) return "À compléter";
  return "En cours";
}

/**
 * « Retour prévu le {date} » / « Date de retour non fixée » (medical.md
 * §3.2, §4.2, §4.4). `dateLabel` vient de l'API quand disponible
 * (`fitness_return_date_label`, déjà formaté par `format_date_fr` côté
 * serveur) — sinon recomposé localement à partir de la date brute, jamais
 * une autre règle que le gabarit fixe de ce texte.
 */
export function fitnessReturnText(params: {
  fitness_status: FitnessStatus;
  fitness_return_date: string | null;
  fitness_return_date_label?: string | null;
  /** Affiche « · dépassé » (Médecin seulement, medical.md §3.2). */
  showOverdue?: boolean;
}): string {
  if (params.fitness_status !== "unfit") return "";
  if (!params.fitness_return_date) return "Date de retour non fixée";
  const label = params.fitness_return_date_label ?? formatDateFrLong(params.fitness_return_date);
  const overdue = params.showOverdue && params.fitness_return_date < todayIso();
  return overdue ? `Retour prévu le ${label} · dépassé` : `Retour prévu le ${label}`;
}

function todayIso(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}

/**
 * « {Séance du …} / {Match contre …} / Hors séance ou match » (medical.md
 * §3.1, §3.4, §4.3). L'API n'expose aujourd'hui que `event_id` sur une
 * blessure (pas le type ni la date/l'adversaire de l'évènement) : tant que
 * `apps.medical.serializers` n'ajoute pas un `event_label` déjà composé
 * (comme le fait déjà en interne `apps.medical.services._notify_injury_reported`
 * pour les notifications), ce texte reste volontairement générique pour un
 * évènement non nul plutôt que d'inventer un intitulé — voir le compte
 * rendu de la tâche.
 */
export function injuryEventLabel(item: Pick<InjuryListItem, "event_id"> & { event_label?: string | null }): string {
  if (item.event_label) return item.event_label;
  if (item.event_id == null) return "Hors séance ou match";
  return "Séance ou match du club";
}
