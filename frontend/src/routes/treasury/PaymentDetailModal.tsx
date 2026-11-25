import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, triggerBlobDownload } from "../../api/client";
import {
  approvePaymentReversal,
  downloadPaymentAttachment,
  downloadPaymentReceipt,
  getPaymentDetail,
  rejectPaymentReversal,
  requestPaymentReversal,
  type PaymentDetail,
  type PaymentReversalHistoryItem,
} from "../../api/treasury";
import { Banner, Button, ConfirmDialog, Modal, StatusBadge, TextArea, useToast } from "../../design-system";
import { AttachmentLink } from "./AttachmentLink";
import { formatAmount, formatDateFr, formatMonthYear } from "./money";

export const PAYMENT_DETAIL_QUERY_KEY = ["treasury", "payment-detail"] as const;

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.";
}

const REVERSAL_BADGE_CLASS: Record<PaymentReversalHistoryItem["status"], string> = {
  pending_approval: "bg-status-warning-bg text-status-warning-fg",
  approved: "bg-status-success-bg text-status-success-fg",
  rejected: "bg-status-danger-bg text-status-danger-fg",
};

/** « 12/03/2026 » à partir d'un horodatage ISO complet. */
function formatStamp(iso: string): string {
  return formatDateFr(iso.slice(0, 10));
}

function ReversalHistory({ items }: { items: PaymentReversalHistoryItem[] }) {
  return (
    <div>
      <p className="mb-2 text-sm font-medium text-text">Demandes d'annulation</p>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.id} className="space-y-1 rounded-md border border-border p-3 text-sm">
            <span
              className={[
                "inline-flex h-[22px] items-center rounded-full px-2 text-xs font-medium",
                REVERSAL_BADGE_CLASS[item.status],
              ].join(" ")}
            >
              {item.status_label}
            </span>
            <p className="break-words text-text">{item.reason || "—"}</p>
            <p className="text-text-muted">
              Demandée par {item.requested_by.name} le {formatStamp(item.requested_at)}
            </p>
            {item.decided_by && item.decided_at && item.status !== "pending_approval" ? (
              <p className="text-text-muted">
                {item.status === "rejected" ? "Refusée" : "Approuvée"} par {item.decided_by.name} le{" "}
                {formatStamp(item.decided_at)}
              </p>
            ) : null}
            {item.status === "rejected" && item.rejection_reason ? (
              <p className="break-words text-text">Motif du refus : {item.rejection_reason}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

export interface PaymentDetailModalProps {
  paymentId: number | null;
  /** Trésorier, adjoint : demander l'annulation, examiner une déclaration (`can_record_payments`). */
  canRecordPayments: boolean;
  /** Président : valider ou refuser l'annulation. */
  canDecideReversals: boolean;
  onClose: () => void;
  /** Niveau d'empilement : 2 quand la modale s'ouvre au-dessus d'une autre (ex. situation d'un membre). */
  level?: 1 | 2;
  /** Ouvre la modale « Déclaration à valider » (niveau 2). */
  onReviewDeclaration: (paymentId: number) => void;
  /** Après demande, validation ou refus d'une annulation : rafraîchit les listes et indicateurs. */
  onChanged: () => void;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="shrink-0 text-text-muted">{label}</span>
      <span className="min-w-0 break-words text-right text-text">{children}</span>
    </div>
  );
}

/**
 * Modale « Détail du paiement » (fiche tresorerie-tableau-de-bord §4.4 ;
 * CDC 4.4.4, 7.2). Un paiement validé n'est jamais supprimé : l'annulation est
 * une demande motivée du Trésorier, validée par le Président (après confirmation), qui crée
 * une écriture d'annulation côté API. Statuts et droits viennent de l'API.
 */
export function PaymentDetailModal({
  paymentId,
  canRecordPayments,
  canDecideReversals,
  onClose,
  level = 1,
  onReviewDeclaration,
  onChanged,
}: PaymentDetailModalProps) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const open = paymentId !== null;

  const [requestOpen, setRequestOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | undefined>();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectError, setRejectError] = useState<string | undefined>();
  const [approveOpen, setApproveOpen] = useState(false);
  const [actionError, setActionError] = useState<string | undefined>();
  const [receiptLoading, setReceiptLoading] = useState(false);

  useEffect(() => {
    if (!open) {
      setRequestOpen(false);
      setReason("");
      setReasonError(undefined);
      setRejectOpen(false);
      setRejectReason("");
      setRejectError(undefined);
      setApproveOpen(false);
      setActionError(undefined);
    }
  }, [open]);

  const query = useQuery({
    queryKey: [...PAYMENT_DETAIL_QUERY_KEY, paymentId],
    queryFn: () => getPaymentDetail(paymentId as number),
    enabled: open,
  });
  const payment: PaymentDetail | undefined = query.data;

  function afterChange(updated: PaymentDetail): void {
    queryClient.setQueryData([...PAYMENT_DETAIL_QUERY_KEY, paymentId], updated);
    onChanged();
  }

  const requestMutation = useMutation({
    mutationFn: (text: string) => requestPaymentReversal(paymentId as number, text),
    onSuccess: (updated) => {
      setRequestOpen(false);
      setReason("");
      afterChange(updated);
      showToast("Demande d'annulation envoyée au Président.");
    },
    onError: (error) => setReasonError(errorMessage(error)),
  });
  const rejectMutation = useMutation({
    mutationFn: (text: string) => rejectPaymentReversal(paymentId as number, text),
    onSuccess: (updated) => {
      setRejectOpen(false);
      setRejectReason("");
      afterChange(updated);
      showToast("Demande d'annulation refusée.");
    },
    onError: (error) => setRejectError(errorMessage(error)),
  });
  const approveMutation = useMutation({
    mutationFn: () => approvePaymentReversal(paymentId as number),
    onSuccess: (updated) => {
      setApproveOpen(false);
      afterChange(updated);
      showToast(`Paiement annulé. Le solde de ${updated.player.name} a été recalculé.`);
    },
    onError: (error) => {
      setApproveOpen(false);
      setActionError(errorMessage(error));
    },
  });

  function submitRequest(): void {
    if (!reason.trim()) {
      setReasonError("Indiquez le motif.");
      return;
    }
    setReasonError(undefined);
    requestMutation.mutate(reason.trim());
  }

  function submitReject(): void {
    if (!rejectReason.trim()) {
      setRejectError("Indiquez le motif du refus.");
      return;
    }
    setRejectError(undefined);
    rejectMutation.mutate(rejectReason.trim());
  }

  async function downloadReceipt(): Promise<void> {
    if (!payment) return;
    setReceiptLoading(true);
    setActionError(undefined);
    try {
      const { blob, filename } = await downloadPaymentReceipt(payment.id);
      triggerBlobDownload(blob, filename);
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setReceiptLoading(false);
    }
  }

  const reversal = payment?.reversal ?? null;
  const reversalPending = reversal?.status === "pending_approval";
  const isPendingDeclaration = payment?.status === "to_validate" && payment.source === "player_declaration";
  const canRequest = Boolean(payment && canRecordPayments && payment.status === "validated" && !reversal);

  const footer = (
    <div className="flex w-full flex-wrap items-center justify-end gap-2">
      <Button variant="secondary" onClick={onClose}>
        Fermer
      </Button>
      {payment && canRequest ? (
        <Button
          variant="secondary"
          onClick={() => {
            setReasonError(undefined);
            setRequestOpen(true);
          }}
        >
          Demander l'annulation
        </Button>
      ) : null}
      {payment && isPendingDeclaration && canRecordPayments ? (
        <Button variant="primary" onClick={() => onReviewDeclaration(payment.id)}>
          Examiner la déclaration
        </Button>
      ) : null}
      {payment?.receipt_available ? (
        <Button variant="secondary" loading={receiptLoading} loadingLabel="Téléchargement…" onClick={() => void downloadReceipt()}>
          Télécharger le reçu
        </Button>
      ) : null}
    </div>
  );

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="Détail du paiement"
        subtitle={payment ? formatAmount(payment.amount, payment.currency) : undefined}
        size="md"
        level={level}
        loading={query.isLoading}
        footer={footer}
      >
        {query.isError ? (
          <div className="space-y-2">
            <p role="alert" className="text-sm text-status-danger-fg">
              Impossible de charger ce paiement.
            </p>
            <Button size="sm" onClick={() => void query.refetch()}>
              Réessayer
            </Button>
          </div>
        ) : payment ? (
          <div className="space-y-4">
            <StatusBadge status={payment.status} />
            {actionError ? <Banner variant="danger">{actionError}</Banner> : null}
            {isPendingDeclaration ? (
              <Banner variant="info">En attente de validation par le trésorier.</Banner>
            ) : null}

            <div className="space-y-2 rounded-md bg-surface-muted p-3 text-sm">
              <Row label="Joueur">{payment.player.name}</Row>
              <Row label="Type">{payment.contribution_type.name}</Row>
              <Row label="Montant">{formatAmount(payment.amount, payment.currency)}</Row>
              <Row label="Mode">{payment.method_label}</Row>
              <Row label="Référence">{payment.reference || "—"}</Row>
              <Row label="Date">{formatDateFr(payment.paid_on)}</Row>
              <Row label="Saisi par">{payment.submitted_by?.name ?? "—"}</Row>
              {payment.validated_at ? <Row label="Validé le">{formatDateFr(payment.validated_at.slice(0, 10))}</Row> : null}
              {payment.receipt_available ? <Row label="Reçu n°">{payment.receipt_number}</Row> : null}
              {payment.rejection_reason ? <Row label="Motif du refus">{payment.rejection_reason}</Row> : null}
            </div>

            {payment.attachment_url ? (
              <AttachmentLink label="Voir la pièce jointe" download={() => downloadPaymentAttachment(payment.id)} />
            ) : null}

            <div>
              <p className="mb-2 text-sm font-medium text-text">Répartition par mois</p>
              {payment.allocations.length === 0 ? (
                <p className="text-sm text-text-muted">Aucune répartition enregistrée.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-text-muted">
                      <th className="py-1 font-medium">Mois</th>
                      <th className="py-1 text-right font-medium">Montant</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payment.allocations.map((allocation) => (
                      <tr key={allocation.period} className="border-t border-border">
                        <td className="py-1 text-text">{formatMonthYear(allocation.period)}</td>
                        <td className="py-1 text-right tabular-nums text-text">
                          {formatAmount(allocation.amount, payment.currency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {reversal ? (
              <div className="space-y-2 rounded-md border border-border p-3 text-sm">
                <p className="font-medium text-text">Annulation : {reversal.status_label}</p>
                <Row label="Motif">{reversal.reason || "—"}</Row>
                <Row label="Demandée par">
                  {reversal.requested_by?.name ?? "—"}
                  {reversal.requested_at ? ` · ${formatDateFr(reversal.requested_at.slice(0, 10))}` : ""}
                </Row>
                {reversal.approved_by ? <Row label="Validée par">{reversal.approved_by.name}</Row> : null}
                {reversal.rejection_reason ? <Row label="Motif du refus">{reversal.rejection_reason}</Row> : null}
                {reversalPending ? (
                  canDecideReversals ? (
                    <div className="flex flex-wrap justify-end gap-2 pt-1">
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setRejectError(undefined);
                          setRejectOpen(true);
                        }}
                      >
                        Refuser
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() => {
                          setApproveOpen(true);
                        }}
                      >
                        Valider l'annulation
                      </Button>
                    </div>
                  ) : (
                    <p className="text-text-muted">En attente de validation par le Président.</p>
                  )
                ) : null}
              </div>
            ) : null}

            {payment.reversal_history && payment.reversal_history.length > 0 ? (
              <ReversalHistory items={payment.reversal_history} />
            ) : null}
          </div>
        ) : null}
      </Modal>

      <Modal
        open={requestOpen}
        onClose={() => setRequestOpen(false)}
        title="Demander l'annulation"
        size="sm"
        level={2}
        isDirty={reason.trim() !== ""}
        isSubmitting={requestMutation.isPending}
        confirmLabel="Envoyer la demande"
        confirmLoadingLabel="Envoi…"
        onConfirm={submitRequest}
      >
        <TextArea
          label="Motif de l'annulation"
          value={reason}
          onChange={setReason}
          error={reasonError}
          help="Le paiement ne sera pas supprimé : une écriture d'annulation sera créée après validation du Président."
        />
      </Modal>

      <Modal
        open={rejectOpen}
        onClose={() => setRejectOpen(false)}
        title="Refuser l'annulation"
        size="sm"
        level={2}
        isDirty={rejectReason.trim() !== ""}
        isSubmitting={rejectMutation.isPending}
        confirmLabel="Refuser l'annulation"
        confirmLoadingLabel="Envoi…"
        onConfirm={submitReject}
      >
        <TextArea label="Motif du refus" value={rejectReason} onChange={setRejectReason} error={rejectError} />
      </Modal>

      <ConfirmDialog
        open={approveOpen}
        title={`Annuler ce paiement de ${payment ? formatAmount(payment.amount, payment.currency) : ""} ?`}
        description={`Une écriture d'annulation sera créée et le solde de ${payment?.player.name ?? "ce joueur"} sera recalculé. Le paiement d'origine reste conservé.`}
        confirmLabel="Annuler le paiement"
        loadingLabel="Annulation…"
        loading={approveMutation.isPending}
        onConfirm={() => approveMutation.mutate()}
        onCancel={() => setApproveOpen(false)}
      />
    </>
  );
}
