import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import {
  downloadPaymentAttachment,
  getPaymentDeclaration,
  previewPaymentDeclaration,
  rejectPaymentDeclaration,
  validatePaymentDeclaration,
  type PaymentPreview,
} from "../../api/treasury";
import { Banner, Button, ConfirmDialog, Modal, StatusBadge, TextArea, useToast } from "../../design-system";
import { AttachmentLink } from "./AttachmentLink";
import { formatAmount, formatDateFr, formatMonthYear } from "./money";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.";
}

function firstName(fullName: string): string {
  return fullName.trim().split(/\s+/)[0] ?? fullName;
}

export interface DeclarationReviewModalProps {
  /** Identifiant du paiement (la déclaration est un paiement à valider) ; `null` = fermée. */
  paymentId: number | null;
  onClose: () => void;
  /** Après validation ou refus : rafraîchit listes et indicateurs. */
  onDone: () => void;
}

/**
 * Modale « Déclaration à valider » (fiche tresorerie-tableau-de-bord §4.5 ;
 * CDC 4.6, 7.2). « Valider » affiche d'abord l'aperçu de répartition calculé
 * par l'API, puis demande une confirmation explicite ; « Refuser » exige un motif.
 */
export function DeclarationReviewModal({ paymentId, onClose, onDone }: DeclarationReviewModalProps) {
  const { showToast } = useToast();
  const open = paymentId !== null;
  const [preview, setPreview] = useState<PaymentPreview | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | undefined>();
  const [actionError, setActionError] = useState<string | undefined>();

  useEffect(() => {
    if (!open) {
      setPreview(null);
      setConfirmOpen(false);
      setRejectOpen(false);
      setReason("");
      setReasonError(undefined);
      setActionError(undefined);
    }
  }, [open]);

  const query = useQuery({
    queryKey: ["treasury", "payment-declaration", paymentId],
    queryFn: () => getPaymentDeclaration(paymentId as number),
    enabled: open,
  });
  const declaration = query.data;

  const previewMutation = useMutation({
    mutationFn: () => previewPaymentDeclaration(paymentId as number),
    onSuccess: (result) => {
      setActionError(undefined);
      setPreview(result);
    },
    onError: (error) => setActionError(errorMessage(error)),
  });
  const validateMutation = useMutation({
    mutationFn: () => validatePaymentDeclaration(paymentId as number),
    onSuccess: (result) => {
      setConfirmOpen(false);
      setPreview(null);
      showToast(`Déclaration validée. Reçu envoyé à ${firstName(result.player.name)}.`);
      onDone();
      onClose();
    },
    onError: (error) => {
      setConfirmOpen(false);
      setPreview(null);
      setActionError(errorMessage(error));
    },
  });
  const rejectMutation = useMutation({
    mutationFn: (text: string) => rejectPaymentDeclaration(paymentId as number, text),
    onSuccess: (result) => {
      setRejectOpen(false);
      showToast(`Déclaration refusée. ${firstName(result.player.name)} a été prévenu.`);
      onDone();
      onClose();
    },
    onError: (error) => setReasonError(errorMessage(error)),
  });

  function submitReject(): void {
    if (!reason.trim()) {
      setReasonError("Indiquez le motif du refus.");
      return;
    }
    setReasonError(undefined);
    rejectMutation.mutate(reason.trim());
  }

  const pending = declaration?.status === "to_validate";

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="Déclaration à valider"
        subtitle={declaration ? declaration.player.name : undefined}
        size="md"
        level={2}
        loading={query.isLoading}
        footer={
          <div className="flex w-full flex-wrap items-center justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Fermer
            </Button>
            {pending ? (
              <>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setReasonError(undefined);
                    setRejectOpen(true);
                  }}
                >
                  Refuser
                </Button>
                <Button
                  variant="primary"
                  loading={previewMutation.isPending}
                  loadingLabel="Calcul…"
                  onClick={() => previewMutation.mutate()}
                >
                  Valider
                </Button>
              </>
            ) : null}
          </div>
        }
      >
        {query.isError ? (
          <div className="space-y-2">
            <p role="alert" className="text-sm text-status-danger-fg">
              Impossible de charger cette déclaration.
            </p>
            <Button size="sm" onClick={() => void query.refetch()}>
              Réessayer
            </Button>
          </div>
        ) : declaration ? (
          <div className="space-y-4">
            <StatusBadge status={declaration.status} />
            {actionError ? <Banner variant="danger">{actionError}</Banner> : null}
            <div className="space-y-2 rounded-md bg-surface-muted p-3 text-sm">
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Type</span>
                <span className="text-text">{declaration.contribution_type.name}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Montant déclaré</span>
                <span className="text-text">{formatAmount(declaration.amount, declaration.currency)}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Référence</span>
                <span className="break-all text-right text-text">{declaration.reference || "—"}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-text-muted">Déclaré le</span>
                <span className="text-text">
                  {formatDateFr((declaration.submitted_at ?? declaration.paid_on).slice(0, 10))}
                </span>
              </div>
            </div>
            {declaration.attachment_url ? (
              <AttachmentLink
                label="Voir la capture du paiement"
                download={() => downloadPaymentAttachment(declaration.id)}
              />
            ) : (
              <p className="text-sm text-text-muted">Aucune capture jointe.</p>
            )}
          </div>
        ) : null}
      </Modal>

      <Modal
        open={preview !== null}
        onClose={() => setPreview(null)}
        title="Répartition du paiement"
        size="md"
        level={2}
        confirmLabel="Continuer"
        onConfirm={() => setConfirmOpen(true)}
      >
        {preview ? (
          <div className="space-y-3 text-sm">
            {preview.is_free_type ? (
              <p className="text-text-muted">Cotisation libre : ce paiement n'entre pas dans le solde.</p>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="text-left text-xs text-text-muted">
                    <th className="py-1 font-medium">Mois</th>
                    <th className="py-1 text-right font-medium">Montant</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.allocations.map((line) => (
                    <tr key={line.period} className="border-t border-border">
                      <td className="py-1 text-text">{formatMonthYear(line.period)}</td>
                      <td className="py-1 text-right tabular-nums text-text">
                        {formatAmount(line.amount, preview.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="text-text">
              Solde actuel : {formatAmount(preview.current.balance, preview.currency)} → Nouveau solde :{" "}
              {formatAmount(preview.after.balance, preview.currency)}
            </p>
            <p className="text-text-muted">{preview.after.reason}</p>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={rejectOpen}
        onClose={() => setRejectOpen(false)}
        title="Refuser la déclaration"
        size="sm"
        level={2}
        isDirty={reason.trim() !== ""}
        isSubmitting={rejectMutation.isPending}
        confirmLabel="Refuser la déclaration"
        confirmLoadingLabel="Envoi…"
        onConfirm={submitReject}
      >
        <TextArea label="Motif du refus" value={reason} onChange={setReason} error={reasonError} />
      </Modal>

      <ConfirmDialog
        open={confirmOpen}
        danger={false}
        title={
          declaration
            ? `Valider ce paiement de ${formatAmount(declaration.amount, declaration.currency)} ?`
            : "Valider ce paiement ?"
        }
        description={
          declaration
            ? `Le paiement de ${declaration.player.name} sera enregistré, son solde recalculé et un reçu lui sera envoyé.`
            : undefined
        }
        confirmLabel="Valider le paiement"
        loadingLabel="Validation…"
        loading={validateMutation.isPending}
        onConfirm={() => validateMutation.mutate()}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
