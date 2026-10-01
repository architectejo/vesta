import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { updateFitness, type FitnessStatus } from "../../api/medical";
import { Modal, SegmentedControl, useToast } from "../../design-system";
import { todayIsoDate } from "./medicalFormat";

export interface FitnessUpdateModalProps {
  open: boolean;
  membershipId: number;
  playerFirstName: string;
  currentStatus: FitnessStatus;
  currentReturnDate: string | null;
  /** Une blessure « En cours » existe pour ce joueur (medical.md §4.4) :
   * « Apte »/« Apte avec restriction » ne peuvent pas être choisis (le
   * design-system n'exposant pas d'option désactivée individuellement dans
   * `SegmentedControl`, le choix est refusé côté gestionnaire et expliqué
   * par l'aide — écart de fidélité signalé au compte rendu). */
  hasOpenInjury: boolean;
  onClose: () => void;
  onUpdated: () => void;
}

const OPTIONS: Array<{ value: FitnessStatus; label: string }> = [
  { value: "fit", label: "Apte" },
  { value: "fit_with_restriction", label: "Apte avec restriction" },
  { value: "unfit", label: "Inapte" },
];

/** « Modifier l'aptitude » (medical.md §4.4), Médecin. */
export function FitnessUpdateModal({
  open,
  membershipId,
  playerFirstName,
  currentStatus,
  currentReturnDate,
  hasOpenInjury,
  onClose,
  onUpdated,
}: FitnessUpdateModalProps) {
  const { showToast } = useToast();
  const [status, setStatus] = useState<FitnessStatus>(currentStatus);
  const [returnDate, setReturnDate] = useState(currentReturnDate ?? "");
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setStatus(currentStatus);
      setReturnDate(currentReturnDate ?? "");
      setError(undefined);
      setSubmitError(undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function handleStatusChange(next: FitnessStatus): void {
    if (hasOpenInjury && next !== "unfit") return;
    setStatus(next);
  }

  async function handleSubmit(): Promise<void> {
    if (status === "unfit" && returnDate && returnDate < todayIsoDate()) {
      setError("La date de retour ne peut pas être dans le passé.");
      return;
    }
    setError(undefined);
    setSubmitting(true);
    setSubmitError(undefined);
    try {
      await updateFitness(membershipId, {
        fitness_status: status,
        fitness_return_date: status === "unfit" ? returnDate || null : null,
      });
      showToast("Aptitude mise à jour.");
      onUpdated();
      onClose();
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  const becameUnfit = status === "unfit" && currentStatus !== "unfit";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Modifier l'aptitude"
      size="sm"
      level={2}
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <SegmentedControl
          label="Aptitude"
          value={status}
          onChange={handleStatusChange}
          options={OPTIONS}
          wrapOnMobile
          help={
            hasOpenInjury
              ? `${playerFirstName} a une blessure en cours. Déclarez son retour depuis la blessure pour le rendre apte.`
              : "Le Coach et le Président voient uniquement l'aptitude et la date de retour prévue."
          }
        />

        {status === "unfit" ? (
          <label className="block text-sm font-medium text-text">
            Date de retour prévue <span className="font-normal text-text-muted">(facultatif)</span>
            <input
              type="date"
              value={returnDate}
              onChange={(e) => setReturnDate(e.target.value)}
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text"
            />
            {error ? <p className="mt-1 text-xs text-status-danger-fg">{error}</p> : null}
          </label>
        ) : null}

        {becameUnfit ? (
          <div className="rounded-md bg-status-warning-bg px-3 py-2 text-sm text-status-warning-fg">
            {playerFirstName} ne pourra plus être composé, réparti en équipe ni placé dans un plan tactique tant
            qu'il est inapte.
          </div>
        ) : null}

        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
