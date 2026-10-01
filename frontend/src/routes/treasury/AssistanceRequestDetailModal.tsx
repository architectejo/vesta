import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import {
  approveSocialAssistanceRequest,
  downloadSocialAssistanceAttachment,
  getSocialAssistanceRequest,
  rejectSocialAssistanceRequest,
  type TreasuryCapabilities,
} from "../../api/treasury";
import { Banner, Button, Modal, StatusBadge, TextArea, useToast } from "../../design-system";
import { AttachmentLink } from "./AttachmentLink";
import { formatAmount, formatDateFr } from "./money";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.";
}

function firstName(fullName: string | null): string {
  if (!fullName) return "Le joueur";
  return fullName.trim().split(/\s+/)[0] ?? fullName;
}

export interface AssistanceRequestDetailModalProps {
  requestId: number | null;
  capabilities: TreasuryCapabilities;
  onClose: () => void;
  onChanged: () => void;
}

/**
 * Modale « Demande d'assistance de {nom} » (fiche
 * `tresorerie-depenses-assistance.md` §4.2 ; CDC 4.5.3 ; 10.2 n° 33 et 37).
 * L'éligibilité, le montant du barème et le délai viennent uniquement de
 * l'API : jamais recalculés ici. L'acceptation ne demande pas de code PIN à
 * cette étape (§9.1 de la fiche, résolu côté API par
 * `SocialAssistanceApproveView`) ; elle crée une dépense « En attente » qui
 * suit ensuite le circuit normal, PIN compris, de la page Dépenses.
 */
export function AssistanceRequestDetailModal({
  requestId,
  capabilities,
  onClose,
  onChanged,
}: AssistanceRequestDetailModalProps) {
  const { showToast } = useToast();
  const open = requestId !== null;

  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectError, setRejectError] = useState<string | undefined>(undefined);
  const [rejecting, setRejecting] = useState(false);
  const [approving, setApproving] = useState(false);
  const [actionError, setActionError] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!open) {
      setRejectOpen(false);
      setRejectReason("");
      setRejectError(undefined);
      setActionError(undefined);
    }
  }, [open]);

  const requestQuery = useQuery({
    queryKey: ["treasury", "social-assistance-request", requestId],
    queryFn: () => getSocialAssistanceRequest(requestId as number),
    enabled: open,
  });
  const request = requestQuery.data;

  function afterAction(): void {
    setActionError(undefined);
    onChanged();
    void requestQuery.refetch();
  }

  async function handleReject(): Promise<void> {
    if (!rejectReason.trim()) {
      setRejectError("Indiquez le motif du refus.");
      return;
    }
    if (!request) return;
    setRejecting(true);
    setRejectError(undefined);
    try {
      await rejectSocialAssistanceRequest(request.id, rejectReason.trim());
      setRejectOpen(false);
      afterAction();
      showToast(`Demande refusée. ${firstName(request.player_name)} a été prévenu.`);
    } catch (error) {
      setRejectError(apiErrorMessage(error));
    } finally {
      setRejecting(false);
    }
  }

  async function handleApprove(): Promise<void> {
    if (!request) return;
    setApproving(true);
    setActionError(undefined);
    try {
      await approveSocialAssistanceRequest(request.id);
      afterAction();
      showToast("Demande acceptée. Une dépense en attente a été créée.");
    } catch (error) {
      setActionError(apiErrorMessage(error));
    } finally {
      setApproving(false);
    }
  }

  const canProcess = capabilities.can_process_assistance_requests;
  const isSubmitted = request?.status === "submitted";
  const currentEligibility = request?.current_eligibility ?? null;
  const canApprove = Boolean(currentEligibility ? currentEligibility.can_be_approved : true);

  function renderFooter() {
    if (!request) return undefined;
    if (!isSubmitted || !canProcess) {
      return (
        <div className="flex w-full items-center justify-end">
          <Button variant="secondary" size="md" onClick={onClose}>
            Fermer
          </Button>
        </div>
      );
    }
    return (
      <div className="flex w-full flex-wrap items-center justify-end gap-2">
        <Button variant="secondary" size="md" onClick={onClose} disabled={approving}>
          Fermer
        </Button>
        <Button variant="secondary" size="md" onClick={() => setRejectOpen(true)} disabled={approving}>
          Refuser
        </Button>
        <Button
          variant="primary"
          size="md"
          disabled={!canApprove}
          loading={approving}
          loadingLabel="Enregistrement…"
          onClick={() => void handleApprove()}
        >
          Accepter la demande
        </Button>
      </div>
    );
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={request ? `Demande d'assistance de ${request.player_name ?? ""}` : "Demande d'assistance"}
        size="lg"
        loading={requestQuery.isLoading}
        footer={renderFooter()}
      >
        {requestQuery.isError ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            Impossible de charger ce détail. Réessayez.
          </p>
        ) : request ? (
          <div className="space-y-4">
            {actionError ? <Banner variant="danger">{actionError}</Banner> : null}

            <div className="flex flex-wrap items-center gap-2">
              {request.status === "submitted" ? (
                request.eligible_at_submission ? (
                  <StatusBadge status="assistance_eligible" />
                ) : (
                  <StatusBadge
                    status="assistance_not_eligible"
                    detail={formatAmount(request.amount_to_regularize_at_submission, request.currency)}
                  />
                )
              ) : (
                <StatusBadge status={request.status === "approved" ? "assistance_approved" : "assistance_rejected"} />
              )}
            </div>

            {request.status === "submitted" && !request.eligible_at_submission ? (
              <Banner variant="warning">
                {firstName(request.player_name)} n'était pas en ordre à la date de l'événement (
                {formatAmount(request.amount_to_regularize_at_submission, request.currency)} à régulariser). Vous
                décidez au cas par cas.
              </Banner>
            ) : null}

            {isSubmitted && canProcess && currentEligibility && !currentEligibility.can_be_approved ? (
              <Banner variant="danger">{currentEligibility.reason}</Banner>
            ) : null}

            <div className="space-y-2 rounded-md bg-surface-muted p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="text-text-muted">Événement</span>
                <span className="text-text">{request.event_type_label}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-text-muted">Date de l'événement</span>
                <span className="text-text">{formatDateFr(request.event_date)}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-text-muted">Description</span>
                <span className="text-right text-text">{request.description || "—"}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-text-muted">Déposée le</span>
                <span className="text-text">{formatDateFr(request.submitted_at.slice(0, 10))}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-text-muted">Montant prévu</span>
                <span className="tabular-nums text-text">{formatAmount(request.planned_amount, request.currency)}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-text-muted">Délai de traitement</span>
                <span className="text-text">{request.processing_days} jours</span>
              </div>
              {request.status === "rejected" && request.rejection_reason ? (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-text-muted">Motif du refus</span>
                  <span className="text-right text-text">{request.rejection_reason}</span>
                </div>
              ) : null}
              {request.status === "approved" && request.expense ? (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-text-muted">Dépense associée</span>
                  <span className="text-text">{request.expense.status_label}</span>
                </div>
              ) : null}
            </div>

            <div>
              <p className="mb-2 text-sm font-medium text-text">Pièce justificative</p>
              <AttachmentLink
                label="Voir la pièce jointe"
                download={() => downloadSocialAssistanceAttachment(request.id)}
              />
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={rejectOpen}
        onClose={() => setRejectOpen(false)}
        title="Refuser la demande"
        size="sm"
        level={2}
        isDirty={rejectReason.trim() !== ""}
        isSubmitting={rejecting}
        confirmLabel="Refuser la demande"
        confirmLoadingLabel="Enregistrement…"
        onConfirm={() => void handleReject()}
      >
        <TextArea label="Motif du refus" value={rejectReason} onChange={setRejectReason} error={rejectError} />
      </Modal>
    </>
  );
}
