import { useState } from "react";
import {
  cancelMembershipApplication,
  getClubIdentity,
  reassignSponsor,
  searchActiveClubPlayers,
  type MembershipApplication,
} from "../../../api/clubs";
import {
  Banner,
  ConfirmDialog,
  Modal,
  PlayerSearch,
  SegmentedControl,
  StatusBadge,
  TextArea,
  useToast,
  type PlayerSearchResult,
} from "../../../design-system";
import { useQuery } from "@tanstack/react-query";
import { formatAmount } from "../../treasury/money";
import { apiMessage, daysSince, feeSummary, personName } from "./applicationText";

type Choice = "reassign" | "cancel";
type Disposition = "refunded" | "kept";

const CHOICES: Array<{ value: Choice; label: string }> = [
  { value: "reassign", label: "Désigner un autre parrain" },
  { value: "cancel", label: "Annuler l'adhésion" },
];

const DISPOSITIONS: Array<{ value: Disposition; label: string }> = [
  { value: "refunded", label: "Rembourser" },
  { value: "kept", label: "Conserver" },
];

/**
 * Modale « Adhésion de {nom} » : décision du Président après un refus du
 * parrain (club-accueil.md §5.5 ; CDC 4.3). Si le parrain est seulement sans
 * réponse, aucune action n'est proposée au-delà de l'alerte (CDC 10.3 n° 71).
 *
 * Toute annulation (remboursement ou conservation) passe par une modale de
 * confirmation explicite (CDC 7.2).
 */
export function MembershipDecisionModal({
  application,
  level = 1,
  onClose,
  onDone,
}: {
  application: MembershipApplication;
  level?: 1 | 2;
  onClose: () => void;
  onDone: () => void;
}) {
  const { showToast } = useToast();
  const identityQuery = useQuery({ queryKey: ["club-identity"], queryFn: getClubIdentity });
  const currency = identityQuery.data?.currency ?? "";

  const refused = application.sponsor_decision === "refused" && application.resolved_at === null;
  const feePaid = application.membership_fee_paid === true;
  const playerName = personName(application.player);

  const [choice, setChoice] = useState<Choice | null>(null);
  const [newSponsor, setNewSponsor] = useState<PlayerSearchResult | null>(null);
  const [disposition, setDisposition] = useState<Disposition | null>(null);
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  async function handleReassign(): Promise<void> {
    if (!newSponsor) {
      setErrors({ sponsor: "Choisissez un parrain." });
      return;
    }
    setErrors({});
    setError(null);
    setSubmitting(true);
    try {
      await reassignSponsor({ application_id: application.id, new_sponsor_membership_id: Number(newSponsor.id) });
      showToast(`${newSponsor.firstName} ${newSponsor.lastName} a été prévenu et doit signer la fiche.`);
      onDone();
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  function handleCancelRequest(): void {
    const next: Record<string, string> = {};
    if (feePaid && !disposition) next.disposition = "Choisissez le sort du paiement.";
    if (!reason.trim()) next.reason = "Indiquez le motif.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    setError(null);
    setConfirmOpen(true);
  }

  async function handleCancel(): Promise<void> {
    if (submitting) return;
    setSubmitting(true);
    try {
      await cancelMembershipApplication({
        application_id: application.id,
        reason: reason.trim(),
        // Sans paiement, il n'y a rien à rembourser : « conservé » n'écrit rien en trésorerie.
        disposition: feePaid ? (disposition as Disposition) : "kept",
      });
      setConfirmOpen(false);
      showToast(`Adhésion de ${playerName} annulée.`);
      onDone();
    } catch (err) {
      setConfirmOpen(false);
      setError(apiMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  const silentDays = daysSince(application.president_alerted_at);
  const confirmProps =
    refused && choice === "reassign"
      ? { confirmLabel: "Désigner", confirmLoadingLabel: "Envoi…", onConfirm: () => void handleReassign() }
      : refused && choice === "cancel"
        ? {
            confirmLabel: "Annuler l'adhésion",
            confirmLoadingLabel: "Annulation…",
            confirmVariant: "danger" as const,
            onConfirm: handleCancelRequest,
          }
        : { hideFooter: !refused || choice === null };

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title={`Adhésion de ${playerName}`}
        size="md"
        level={level}
        isDirty={newSponsor !== null || reason !== ""}
        isSubmitting={submitting}
        cancelLabel={refused && choice !== null ? "Annuler" : "Fermer"}
        {...confirmProps}
      >
        <div className="space-y-4">
          {error ? <Banner variant="danger">{error}</Banner> : null}
          <div className="space-y-1 text-sm text-text">
            <p>
              Parrain actuel : <span className="font-medium">{personName(application.sponsor)}</span>
            </p>
            <p>Frais d'adhésion : {feeSummary(application, currency)}</p>
          </div>
          {refused ? (
            <>
              <div className="space-y-1">
                <StatusBadge status="refused" detail="Parrainage" />
                <p className="text-sm text-text">Motif : {application.sponsor_refused_reason}</p>
              </div>
              <SegmentedControl label="Décision" value={choice} onChange={setChoice} options={CHOICES} />
              {choice === "reassign" ? (
                <div>
                  <p className="mb-1 text-sm font-medium text-text">Nouveau parrain</p>
                  <PlayerSearch
                    value={newSponsor}
                    onChange={setNewSponsor}
                    searchPlayers={searchActiveClubPlayers}
                    ariaLabel="Nouveau parrain"
                    placeholder="Nom ou numéro du joueur"
                  />
                  {errors.sponsor ? <p className="mt-1 text-xs text-status-danger-fg">{errors.sponsor}</p> : null}
                </div>
              ) : null}
              {choice === "cancel" ? (
                <div className="space-y-3">
                  {feePaid ? (
                    <>
                      <SegmentedControl
                        label="Sort du paiement d'adhésion"
                        value={disposition}
                        onChange={setDisposition}
                        options={DISPOSITIONS}
                      />
                      {errors.disposition ? (
                        <p className="text-xs text-status-danger-fg">{errors.disposition}</p>
                      ) : null}
                      <p className="text-xs text-text-muted">
                        Un paiement validé n'est jamais supprimé : un remboursement passe par une écriture
                        d'annulation.
                      </p>
                    </>
                  ) : null}
                  <TextArea label="Motif" value={reason} onChange={setReason} error={errors.reason} />
                </div>
              ) : null}
            </>
          ) : application.sponsor_decision === "pending" && application.resolved_at === null ? (
            <>
              <StatusBadge
                status="pending"
                detail={silentDays !== null ? `Sans réponse depuis ${silentDays} jours` : "En attente du parrain"}
              />
              <p className="text-sm text-text-muted">
                Aucune action n'est possible pour l'instant : le dossier reste en attente de la signature du
                parrain.
              </p>
            </>
          ) : (
            <Banner variant="info">Ce dossier n'est plus en attente.</Banner>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmOpen}
        title={`Annuler l'adhésion de ${playerName} ?`}
        description={
          feePaid && disposition === "refunded"
            ? `Le dossier sera clos et le paiement d'adhésion${
                application.membership_fee_amount
                  ? ` de ${formatAmount(application.membership_fee_amount, currency)}`
                  : ""
              } remboursé par une écriture d'annulation. Cette action est définitive.`
            : "Le dossier sera clos. Cette action est définitive."
        }
        confirmLabel="Confirmer l'annulation"
        loadingLabel="Annulation…"
        loading={submitting}
        onConfirm={() => void handleCancel()}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
