import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { declareInjuryReturn } from "../../api/medical";
import { Modal, useToast } from "../../design-system";
import { todayIsoDate } from "./medicalFormat";

export interface InjuryReturnDialogProps {
  open: boolean;
  injuryId: number;
  playerFirstName: string;
  /** Blessures encore en cours pour ce joueur, en plus de celle-ci (connu
   * du contexte appelant — fiche de santé ou blessure, medical.md §4.9). */
  hasOtherOpenInjury: boolean;
  injuryReportedDate: string;
  onClose: () => void;
  onDeclared: () => void;
}

/** « Déclarer le retour » (medical.md §4.9, CDC 4.12 étape 5), Médecin. */
export function InjuryReturnDialog({
  open,
  injuryId,
  playerFirstName,
  hasOtherOpenInjury,
  injuryReportedDate,
  onClose,
  onDeclared,
}: InjuryReturnDialogProps) {
  const { showToast } = useToast();
  const [returnDate, setReturnDate] = useState(todayIsoDate());
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setReturnDate(todayIsoDate());
      setError(undefined);
    }
  }, [open]);

  async function handleConfirm(): Promise<void> {
    const today = todayIsoDate();
    if (returnDate > today) {
      setError("La date du retour ne peut pas être dans le futur.");
      return;
    }
    if (returnDate < injuryReportedDate) {
      setError("La date du retour ne peut pas être avant la blessure.");
      return;
    }
    setSubmitting(true);
    setError(undefined);
    try {
      await declareInjuryReturn(injuryId, { return_date: returnDate });
      showToast(
        hasOtherOpenInjury
          ? `Retour déclaré. ${playerFirstName} reste inapte.`
          : `Retour déclaré. ${playerFirstName} est de nouveau apte.`,
      );
      onDeclared();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Déclarer le retour de ${playerFirstName} ?`}
      size="sm"
      level={2}
      isSubmitting={submitting}
      cancelLabel="Annuler"
      confirmLabel="Déclarer le retour"
      confirmVariant="primary"
      onConfirm={() => void handleConfirm()}
    >
      <div className="space-y-3">
        <p className="text-sm text-text-muted">
          {hasOtherOpenInjury
            ? `Cette blessure sera close, mais ${playerFirstName} restera inapte : une autre blessure est en cours.`
            : "Il redeviendra apte et pourra de nouveau être composé."}
        </p>
        <label className="block text-sm font-medium text-text">
          Date du retour
          <input
            type="date"
            value={returnDate}
            onChange={(e) => setReturnDate(e.target.value)}
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text"
          />
        </label>
        {error ? <p className="text-xs text-status-danger-fg">{error}</p> : null}
      </div>
    </Modal>
  );
}
