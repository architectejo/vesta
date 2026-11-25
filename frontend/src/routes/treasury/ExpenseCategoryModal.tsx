import { useState } from "react";
import type { ExpenseCategory, ExpenseCategoryInput } from "../../api/treasury";
import { toApiAmount } from "./money";
import { Checkbox, MoneyField, Modal, TextField } from "../../design-system";

export interface ExpenseCategoryModalProps {
  open: boolean;
  category?: ExpenseCategory;
  currency: string;
  isSubmitting: boolean;
  submitError?: string;
  onClose: () => void;
  onSubmit: (input: ExpenseCategoryInput) => void;
}

interface FormErrors {
  name?: string;
}

/**
 * Modale « Catégorie de dépense » — création ou modification (fiche
 * `tresorerie-depenses-assistance.md` §3.5 ; CDC 4.5.1). Réservée au
 * Président et au Trésorier (`can_manage_expense_categories`).
 */
export function ExpenseCategoryModal({
  open,
  category,
  currency,
  isSubmitting,
  submitError,
  onClose,
  onSubmit,
}: ExpenseCategoryModalProps) {
  const [name, setName] = useState(category?.name ?? "");
  const [ceiling, setCeiling] = useState(category?.ceiling ?? "");
  const [receiptRequired, setReceiptRequired] = useState(category?.receipt_required ?? true);
  const [goodStandingOnly, setGoodStandingOnly] = useState(category?.good_standing_only ?? false);
  const [errors, setErrors] = useState<FormErrors>({});

  const isDirty = Boolean(
    name !== (category?.name ?? "") ||
      ceiling !== (category?.ceiling ?? "") ||
      receiptRequired !== (category?.receipt_required ?? true) ||
      goodStandingOnly !== (category?.good_standing_only ?? false),
  );

  function submit(): void {
    const trimmed = name.trim();
    if (!trimmed) {
      setErrors({ name: "Ce champ est obligatoire." });
      return;
    }
    setErrors({});
    onSubmit({
      name: trimmed,
      ceiling: ceiling.trim() === "" ? null : toApiAmount(ceiling),
      receipt_required: receiptRequired,
      good_standing_only: goodStandingOnly,
    });
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={category ? "Modifier la catégorie" : "Nouvelle catégorie de dépense"}
      size="md"
      isDirty={isDirty}
      isSubmitting={isSubmitting}
      confirmLabel="Enregistrer"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={submit}
    >
      <div className="space-y-4">
        <TextField label="Nom" value={name} onChange={setName} error={errors.name} disabled={isSubmitting} />
        <MoneyField
          label="Plafond"
          currency={currency}
          optional
          value={ceiling}
          onChange={setCeiling}
          disabled={isSubmitting}
        />
        <Checkbox
          label="Justificatif obligatoire"
          checked={receiptRequired}
          onChange={setReceiptRequired}
          disabled={isSubmitting}
        />
        <Checkbox
          label="Réservée aux membres en ordre"
          checked={goodStandingOnly}
          onChange={setGoodStandingOnly}
          disabled={isSubmitting}
        />
        {submitError ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            {submitError}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}
