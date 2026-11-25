import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { downloadSocialAssistanceAttachment, getSocialAssistanceRequest } from "../../api/treasury";
import { Modal, StatusBadge } from "../../design-system";
import { AttachmentLink } from "../treasury/AttachmentLink";
import { formatAmount, formatDateFr } from "../treasury/money";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="shrink-0 text-text-muted">{label}</span>
      <span className="min-w-0 break-words text-right text-text">{children}</span>
    </div>
  );
}

export interface MyAssistanceRequestModalProps {
  requestId: number | null;
  onClose: () => void;
}

/** Détail d'une de ses demandes d'assistance : état et motif de refus (comptes-mon-profil.md §3 point 3). */
export function MyAssistanceRequestModal({ requestId, onClose }: MyAssistanceRequestModalProps) {
  const open = requestId !== null;
  const query = useQuery({
    queryKey: ["treasury", "social-assistance-request", requestId],
    queryFn: () => getSocialAssistanceRequest(requestId as number),
    enabled: open,
  });
  const request = query.data;

  return (
    <Modal open={open} onClose={onClose} title="Demande d'assistance" size="md" loading={query.isLoading} cancelLabel="Fermer">
      {query.isError ? (
        <p role="alert" className="text-sm text-status-danger-fg">
          Impossible de charger ce détail. Réessayez.
        </p>
      ) : request ? (
        <div className="space-y-4">
          <StatusBadge
            status={
              request.status === "approved"
                ? "assistance_approved"
                : request.status === "rejected"
                  ? "assistance_rejected"
                  : request.eligible_at_submission
                    ? "assistance_eligible"
                    : "assistance_not_eligible"
            }
          />
          <div className="space-y-2 rounded-md bg-surface-muted p-3 text-sm">
            <Row label="Événement">{request.event_type_label}</Row>
            <Row label="Date de l'événement">{formatDateFr(request.event_date)}</Row>
            <Row label="Description">{request.description || "—"}</Row>
            <Row label="Déposée le">{formatDateFr(request.submitted_at.slice(0, 10))}</Row>
            <Row label="Montant prévu">
              <span className="tabular-nums">{formatAmount(request.planned_amount, request.currency)}</span>
            </Row>
            <Row label="Délai de traitement">{request.processing_days} jours</Row>
            <Row label="État">{request.status_label}</Row>
            {request.status === "rejected" && request.rejection_reason ? (
              <Row label="Motif du refus">{request.rejection_reason}</Row>
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
  );
}
