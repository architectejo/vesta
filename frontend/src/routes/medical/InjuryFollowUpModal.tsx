import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { addInjuryFollowUp } from "../../api/medical";
import { Modal, TextArea, useToast } from "../../design-system";
import { todayIsoDate } from "./medicalFormat";

export interface InjuryFollowUpModalProps {
  open: boolean;
  injuryId: number;
  injuryReportedDate: string;
  onClose: () => void;
  onAdded: () => void;
}

/** « Ajouter un suivi » (medical.md §4.8, CDC 4.12 étape 4), Médecin. */
export function InjuryFollowUpModal({ open, injuryId, injuryReportedDate, onClose, onAdded }: InjuryFollowUpModalProps) {
  const { showToast } = useToast();
  const [entryDate, setEntryDate] = useState(todayIsoDate());
  const [note, setNote] = useState("");
  const [returnDate, setReturnDate] = useState(todayIsoDate());
  const [errors, setErrors] = useState<{ entryDate?: string; note?: string; returnDate?: string }>({});
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setEntryDate(todayIsoDate());
      setNote("");
      setReturnDate(todayIsoDate());
      setErrors({});
      setSubmitError(undefined);
    }
  }, [open]);

  function validate(): boolean {
    const next: typeof errors = {};
    const today = todayIsoDate();
    if (!entryDate) next.entryDate = "Ce champ est obligatoire.";
    else if (entryDate > today) next.entryDate = "La date ne peut pas être dans le futur.";
    else if (entryDate < injuryReportedDate) next.entryDate = "La date ne peut pas être avant la blessure.";
    if (!note.trim()) next.note = "Ce champ est obligatoire.";
    if (returnDate && returnDate < today) next.returnDate = "La date de retour ne peut pas être dans le passé.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(): Promise<void> {
    if (!validate()) return;
    setSubmitting(true);
    setSubmitError(undefined);
    try {
      await addInjuryFollowUp(injuryId, {
        entry_date: entryDate,
        note: note.trim(),
        fitness_return_date: returnDate || null,
      });
      showToast("Suivi ajouté.");
      onAdded();
      onClose();
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Ajouter un suivi"
      size="md"
      isSubmitting={submitting}
      confirmLabel="Ajouter"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <label className="block text-sm font-medium text-text">
          Date
          <input
            type="date"
            value={entryDate}
            onChange={(e) => setEntryDate(e.target.value)}
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text"
          />
          {errors.entryDate ? <p className="mt-1 text-xs text-status-danger-fg">{errors.entryDate}</p> : null}
        </label>

        <TextArea
          label="Suivi"
          value={note}
          onChange={setNote}
          placeholder="Évolution, soins, examens."
          error={errors.note}
        />

        <label className="block text-sm font-medium text-text">
          Nouvelle date de retour prévue <span className="font-normal text-text-muted">(facultatif)</span>
          <input
            type="date"
            value={returnDate}
            onChange={(e) => setReturnDate(e.target.value)}
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text"
          />
          {errors.returnDate ? <p className="mt-1 text-xs text-status-danger-fg">{errors.returnDate}</p> : null}
        </label>

        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
