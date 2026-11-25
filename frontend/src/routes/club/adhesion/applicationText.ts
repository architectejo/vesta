import type { MembershipApplication } from "../../../api/clubs";
import { ApiError } from "../../../api/client";
import { formatAmount, formatDateFr } from "../../treasury/money";

export function personName(person: { first_name: string; last_name: string } | null | undefined): string {
  return person ? `${person.first_name} ${person.last_name}` : "—";
}

/** « Payés le 12/03/2026 · 5 USD » ou « Non payés », d'après les données de l'API. */
export function feeSummary(application: MembershipApplication, currency: string): string {
  if (!application.membership_fee_paid) return "Non payés";
  const date = application.membership_fee_paid_on ? formatDateFr(application.membership_fee_paid_on) : null;
  const amount = application.membership_fee_amount
    ? formatAmount(application.membership_fee_amount, currency)
    : null;
  return ["Payés", date ? `le ${date}` : null, amount ? `· ${amount}` : null].filter(Boolean).join(" ");
}

/** Jours écoulés depuis une date ISO (affichage « Sans réponse depuis n jours »). */
export function daysSince(iso: string | null, now: Date = new Date()): number | null {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  return Math.max(0, Math.floor((now.getTime() - then.getTime()) / 86_400_000));
}

export function apiMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.detail
    : "Une erreur est survenue de notre côté. Réessayez dans un instant.";
}
