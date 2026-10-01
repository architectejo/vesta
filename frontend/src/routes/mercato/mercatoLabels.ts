import type { TransferOffer, TransferOfferStatus } from "../../api/mercato";
import type { StatusKey, TransferTimelineStep } from "../../design-system";

/** Clé de `StatusBadge` pour un statut d'offre déjà résolu par l'API selon
 * le club de l'utilisateur (fiche `mercato.md` §8) : jamais recalculé ici. */
export function offerStatusKey(status: TransferOfferStatus): StatusKey {
  switch (status) {
    case "sent":
      return "transfer_pending";
    case "accepted_by_player":
      return "transfer_accepted";
    case "declined_by_player":
      return "transfer_refused";
    case "blocked_debt":
      return "transfer_blocked";
    case "awaiting_quitus":
      return "transfer_awaiting_quitus";
    case "completed":
      return "transfer_done";
    case "cancelled":
      return "transfer_cancelled";
    default:
      return "transfer_pending";
  }
}

function fmt(iso: string | null): string | undefined {
  if (!iso) return undefined;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return undefined;
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

export interface TimelineLabels {
  responseStepLabel: string;
  verificationStepLabel: string;
}

/**
 * Chronologie à 5 étapes (§4.3, §4.4). Deux libellés changent selon le
 * spectateur (joueur : « Votre réponse » / dirigeant : « Réponse du
 * joueur »), le reste est identique. Aucune règle de blocage ou de montant
 * n'est évaluée ici : tout vient de `offer` (déjà filtré par l'API selon
 * le club qui regarde, §2.1).
 */
export function buildTransferTimeline(offer: TransferOffer, labels: TimelineLabels): TransferTimelineStep[] {
  const steps: TransferTimelineStep[] = [
    { key: "offer", label: "Offre reçue", state: "done", date: fmt(offer.created_at) },
  ];

  if (offer.status === "sent") {
    steps.push({ key: "response", label: labels.responseStepLabel, state: "upcoming" });
    steps.push({ key: "verification", label: labels.verificationStepLabel, state: "upcoming" });
    steps.push({ key: "quitus", label: "Quitus", state: "upcoming" });
    steps.push({ key: "done", label: "Transfert effectué", state: "upcoming" });
    return steps;
  }

  if (offer.status === "declined_by_player") {
    steps.push({ key: "response", label: labels.responseStepLabel, state: "blocked", date: fmt(offer.player_decision_at) });
    steps.push({ key: "verification", label: labels.verificationStepLabel, state: "upcoming" });
    steps.push({ key: "quitus", label: "Quitus", state: "upcoming" });
    steps.push({ key: "done", label: "Transfert effectué", state: "upcoming" });
    return steps;
  }

  steps.push({ key: "response", label: labels.responseStepLabel, state: "done", date: fmt(offer.player_decision_at) });

  if (offer.status === "accepted_by_player") {
    steps.push({ key: "verification", label: labels.verificationStepLabel, state: "current", detail: "Vérification en cours…" });
    steps.push({ key: "quitus", label: "Quitus", state: "upcoming" });
    steps.push({ key: "done", label: "Transfert effectué", state: "upcoming" });
    return steps;
  }

  if (offer.status === "blocked_debt" || offer.status === "awaiting_quitus") {
    const detail =
      offer.status === "blocked_debt"
        ? offer.debt_amount
          ? `Bloquée : En dette : ${offer.debt_amount}`
          : "Bloquée : situation financière à régulariser"
        : "En attente du quitus de son club actuel";
    steps.push({ key: "verification", label: labels.verificationStepLabel, state: "blocked", detail });
    steps.push({ key: "quitus", label: "Quitus", state: "upcoming" });
    steps.push({ key: "done", label: "Transfert effectué", state: "upcoming" });
    return steps;
  }

  // completed
  steps.push({ key: "verification", label: labels.verificationStepLabel, state: "done" });
  steps.push({ key: "quitus", label: "Quitus", state: "done", date: fmt(offer.completed_at) });
  steps.push({ key: "done", label: "Transfert effectué", state: "done", date: fmt(offer.completed_at) });
  return steps;
}
