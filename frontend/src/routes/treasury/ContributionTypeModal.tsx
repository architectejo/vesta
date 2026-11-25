import { useState } from "react";
import { ApiError } from "../../api/client";
import type {
  ContributionNature,
  ContributionPeriodicity,
  ContributionType,
  ContributionTypeInput,
} from "../../api/treasury";
import { Button, Modal, MoneyField, TextField } from "../../design-system";
import { isPositiveAmount, toApiAmount } from "./money";
import { NATURE_LABELS, PERIODICITY_OPTIONS } from "./contributionTypeLabels";

interface Props {
  open: boolean;
  type?: ContributionType;
  canEdit: boolean;
  /** Devise du club, venant de l'API. */
  currency: string;
  isSubmitting: boolean;
  /** Message d'erreur renvoyé par l'enregistrement, affiché dans la modale. */
  submitError?: string;
  onClose: () => void;
  onSubmit: (input: ContributionTypeInput) => void;
}

interface FormErrors {
  name?: string;
  amount?: string;
  dueDay?: string;
}

const NATURES: ContributionNature[] = ["mandatory", "free"];
const DEFAULT_DUE_DAY = "10";

function hasDueDay(periodicity: ContributionPeriodicity): boolean {
  return periodicity === "monthly" || periodicity === "annual";
}

interface FormValues {
  name: string;
  nature: ContributionNature;
  amount: string;
  periodicity: ContributionPeriodicity;
  dueDay: string;
}

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {};
  if (!values.name.trim()) {
    errors.name = "Ce champ est obligatoire.";
  }
  if (values.nature === "mandatory" && !isPositiveAmount(values.amount)) {
    errors.amount = "Saisissez un montant supérieur à 0.";
  }
  if (
    hasDueDay(values.periodicity) &&
    (!values.dueDay || Number(values.dueDay) < 1 || Number(values.dueDay) > 28)
  ) {
    errors.dueDay = "Saisissez un jour entre 1 et 28.";
  }
  return errors;
}

/**
 * Formulaire (et consultation en lecture seule) d'un type de cotisation
 * (cahier des charges 4.4.1). L'appelant le monte à l'ouverture, avec une clé
 * propre au type, pour repartir des valeurs du type consulté.
 */
export function ContributionTypeModal({
  open,
  type,
  canEdit,
  currency,
  isSubmitting,
  submitError,
  onClose,
  onSubmit,
}: Props) {
  const [name, setName] = useState(type?.name ?? "");
  const [nature, setNature] = useState<ContributionNature>(type?.nature ?? "mandatory");
  const [amount, setAmount] = useState(type?.amount ?? "");
  const [periodicity, setPeriodicity] = useState<ContributionPeriodicity>(type?.periodicity ?? "monthly");
  const [dueDay, setDueDay] = useState(type?.due_day ? String(type.due_day) : DEFAULT_DUE_DAY);
  const [errors, setErrors] = useState<FormErrors>({});

  function submit(): void {
    const nextErrors = validate({ name, nature, amount, periodicity, dueDay });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    onSubmit({
      name: name.trim(),
      nature,
      amount: amount.trim() === "" ? null : toApiAmount(amount),
      periodicity,
      due_day: hasDueDay(periodicity) ? Number(dueDay) : null,
      scope: type?.scope ?? "all",
    });
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={type ? "Modifier le type de cotisation" : "Nouveau type de cotisation"}
      size="md"
      isSubmitting={isSubmitting}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Annuler
          </Button>
          {canEdit ? (
            <Button variant="primary" onClick={submit} loading={isSubmitting}>
              Enregistrer
            </Button>
          ) : null}
        </>
      }
    >
      {!canEdit ? (
        <p className="mb-4 text-sm text-text-muted">Ce type est consultable en lecture seule.</p>
      ) : null}
      <div className="space-y-4">
        <TextField label="Nom" value={name} onChange={setName} disabled={!canEdit} error={errors.name} />
        <fieldset disabled={!canEdit}>
          <legend className="mb-1 block text-sm font-medium text-text">Nature</legend>
          <div className="flex gap-2">
            {NATURES.map((value) => (
              <Button
                key={value}
                variant={nature === value ? "primary" : "secondary"}
                size="sm"
                aria-pressed={nature === value}
                onClick={() => setNature(value)}
              >
                {NATURE_LABELS[value]}
              </Button>
            ))}
          </div>
          <p className="mt-1 text-sm text-text-muted">Seule une cotisation obligatoire crée une dette.</p>
        </fieldset>
        <MoneyField
          label={nature === "free" ? "Montant suggéré" : "Montant"}
          currency={currency}
          value={amount}
          onChange={setAmount}
          optional={nature === "free"}
          disabled={!canEdit || Boolean(type)}
          help={type ? "Le montant est conservé pour les échéances déjà générées." : undefined}
          error={errors.amount}
        />
        <label className="block text-sm font-medium text-text">
          Périodicité
          <select
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
            value={periodicity}
            onChange={(event) => setPeriodicity(event.target.value as ContributionPeriodicity)}
            disabled={!canEdit}
          >
            {PERIODICITY_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {hasDueDay(periodicity) ? (
          <TextField
            label="Jour d'échéance"
            type="number"
            min="1"
            max="28"
            value={dueDay}
            onChange={setDueDay}
            disabled={!canEdit}
            error={errors.dueDay}
          />
        ) : null}
        {submitError ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            {submitError}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}

export function contributionTypeError(error: unknown): string {
  return error instanceof ApiError
    ? error.detail
    : "Une erreur est survenue de notre côté. Réessayez dans un instant.";
}
