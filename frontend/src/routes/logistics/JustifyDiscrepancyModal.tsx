import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import type { DiscrepancyReason, InventoryLine } from "../../api/logistics";
import { Modal, SegmentedControl } from "../../design-system";
import { DISCREPANCY_REASON_OPTIONS } from "./materielLabels";

export interface JustifyDiscrepancyModalProps {
  line: InventoryLine | null;
  onClose: () => void;
  onSubmit: (reason: DiscrepancyReason) => Promise<void>;
}

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

/** « Justifier l'écart » (fiche `logistique.md` §4.7, Intendant). */
export function JustifyDiscrepancyModal({ line, onClose, onSubmit }: JustifyDiscrepancyModalProps) {
  const open = line !== null;
  const [reason, setReason] = useState<DiscrepancyReason | null>(null);
  const [reasonError, setReasonError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setReason((line?.discrepancy_reason || null) as DiscrepancyReason | null);
    setReasonError(undefined);
    setSubmitError(undefined);
  }, [open, line]);

  async function handleSubmit(): Promise<void> {
    if (!reason) {
      setReasonError("Choisissez la cause de l'écart.");
      return;
    }
    setSubmitting(true);
    setSubmitError(undefined);
    try {
      await onSubmit(reason);
    } catch (error) {
      setSubmitError(apiErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  if (!line) return null;

  const sign = line.discrepancy > 0 ? "+" : "";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Justifier l'écart"
      subtitle={line.article_name}
      size="sm"
      level={2}
      isDirty={reason !== (line.discrepancy_reason || null)}
      isSubmitting={submitting}
      confirmLabel="Justifier"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <p className="tabular-nums text-base text-text">
          Stock théorique : {line.theoretical_quantity} · Stock compté : {line.physical_quantity} · Écart : {sign}
          {line.discrepancy}
        </p>
        <SegmentedControl
          label="Cause de l'écart"
          value={reason}
          onChange={setReason}
          options={DISCREPANCY_REASON_OPTIONS}
          error={reasonError}
        />
        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
