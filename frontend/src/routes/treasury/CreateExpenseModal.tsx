import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchActiveClubPlayers } from "../../api/clubs";
import { ApiError } from "../../api/client";
import { getExpenseCategories, type ExpenseCategory } from "../../api/treasury";
import {
  Banner,
  Modal,
  MoneyField,
  PlayerSearch,
  TextArea,
  TextField,
  type PlayerSearchResult,
} from "../../design-system";
import { describeExpenseCategory } from "./expenseLabels";

const CATEGORIES_QUERY_KEY = ["treasury", "expense-categories", "active"] as const;

export interface CreateExpenseFormValues {
  categoryId: number;
  amount: string;
  beneficiaryName: string;
  beneficiaryMembershipId: number | null;
  reason: string;
  expenseDate: string;
  attachment: File | null;
}

export interface CreateExpenseModalProps {
  open: boolean;
  currency: string;
  isSubmitting: boolean;
  submitError?: string;
  onClose: () => void;
  onSubmit: (values: CreateExpenseFormValues) => void;
}

interface FormErrors {
  category?: string;
  amount?: string;
  beneficiary?: string;
  reason?: string;
  expenseDate?: string;
}

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Impossible de charger les catégories. Réessayez.";
}

/**
 * Modale « Saisir une dépense » (fiche `tresorerie-depenses-assistance.md`
 * §3.2 ; CDC 4.5.2). Réservée au Trésorier et à l'adjoint
 * (`can_submit_expenses`). Le bénéficiaire accepte un joueur (`PlayerSearch`,
 * jamais de `<select>` de joueurs) et/ou un nom libre : les deux champs sont
 * acceptés par l'API (`ExpenseCreateSerializer.beneficiary_name` /
 * `beneficiary_membership_id`), point ouvert §9.4 de la fiche.
 */
export function CreateExpenseModal({
  open,
  currency,
  isSubmitting,
  submitError,
  onClose,
  onSubmit,
}: CreateExpenseModalProps) {
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [amount, setAmount] = useState("");
  const [player, setPlayer] = useState<PlayerSearchResult | null>(null);
  const [beneficiaryName, setBeneficiaryName] = useState("");
  const [reason, setReason] = useState("");
  const [expenseDate, setExpenseDate] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const [errors, setErrors] = useState<FormErrors>({});

  const categoriesQuery = useQuery({
    queryKey: CATEGORIES_QUERY_KEY,
    queryFn: () => getExpenseCategories("active"),
    enabled: open,
  });
  const categories = categoriesQuery.data ?? [];
  const selectedCategory: ExpenseCategory | undefined = categories.find((c) => c.id === categoryId);

  useEffect(() => {
    if (!open) {
      setCategoryId("");
      setAmount("");
      setPlayer(null);
      setBeneficiaryName("");
      setReason("");
      setExpenseDate("");
      setAttachment(null);
      setErrors({});
    }
  }, [open]);

  const isDirty = Boolean(
    categoryId !== "" || amount || player || beneficiaryName || reason || expenseDate || attachment,
  );

  function handlePlayerChange(next: PlayerSearchResult | null): void {
    setPlayer(next);
    if (next) setBeneficiaryName(`${next.firstName} ${next.lastName}`);
  }

  function submit(): void {
    const nextErrors: FormErrors = {};
    if (categoryId === "") nextErrors.category = "Choisissez une catégorie.";
    const numericAmount = Number(amount.replace(",", "."));
    if (!amount || Number.isNaN(numericAmount) || numericAmount <= 0) {
      nextErrors.amount = "Saisissez un montant supérieur à 0.";
    }
    if (!beneficiaryName.trim()) nextErrors.beneficiary = "Ce champ est obligatoire.";
    if (!reason.trim()) nextErrors.reason = "Ce champ est obligatoire.";
    if (!expenseDate) nextErrors.expenseDate = "Ce champ est obligatoire.";
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    onSubmit({
      categoryId: Number(categoryId),
      amount: amount.replace(",", "."),
      beneficiaryName: beneficiaryName.trim(),
      beneficiaryMembershipId: player ? Number(player.id) : null,
      reason: reason.trim(),
      expenseDate,
      attachment,
    });
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Saisir une dépense"
      size="md"
      isDirty={isDirty}
      isSubmitting={isSubmitting}
      confirmLabel="Enregistrer la dépense"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={submit}
    >
      <div className="space-y-4">
        {submitError ? <Banner variant="danger">{submitError}</Banner> : null}

        <label className="block text-sm font-medium text-text" htmlFor="create-expense-category">
          Catégorie
          <select
            id="create-expense-category"
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
            value={categoryId}
            onChange={(event) => setCategoryId(event.target.value ? Number(event.target.value) : "")}
            disabled={categoriesQuery.isLoading}
          >
            <option value="" disabled>
              Choisissez une catégorie
            </option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </label>
        {categoriesQuery.isError ? (
          <p role="alert" className="text-xs text-status-danger-fg">
            {apiErrorMessage(categoriesQuery.error)}
          </p>
        ) : null}
        {errors.category ? <p className="text-xs text-status-danger-fg">{errors.category}</p> : null}
        {selectedCategory ? (
          <p className="rounded-md bg-surface-muted p-2 text-xs text-text-muted">
            {describeExpenseCategory(selectedCategory, currency)}
          </p>
        ) : null}

        <MoneyField label="Montant" currency={currency} value={amount} onChange={setAmount} error={errors.amount} />

        <div>
          <label className="mb-1 block text-sm font-medium text-text" htmlFor="create-expense-player">
            Joueur bénéficiaire <span className="font-normal text-text-muted">(facultatif)</span>
          </label>
          <PlayerSearch
            value={player}
            onChange={handlePlayerChange}
            searchPlayers={searchActiveClubPlayers}
            ariaLabel="Nom ou numéro du joueur bénéficiaire"
          />
        </div>

        <TextField
          label="Nom du bénéficiaire"
          value={beneficiaryName}
          onChange={setBeneficiaryName}
          error={errors.beneficiary}
          help="Rempli automatiquement si vous choisissez un joueur ; modifiable."
        />

        <TextArea label="Motif" value={reason} onChange={setReason} error={errors.reason} />

        <TextField
          label="Date"
          type="date"
          value={expenseDate}
          onChange={setExpenseDate}
          error={errors.expenseDate}
        />

        <div>
          <label className="mb-1 block text-sm font-medium text-text" htmlFor="create-expense-attachment">
            Justificatif <span className="font-normal text-text-muted">(facultatif)</span>
          </label>
          <input
            id="create-expense-attachment"
            type="file"
            accept=".jpg,.jpeg,.png,.webp,.pdf"
            onChange={(event) => setAttachment(event.target.files?.[0] ?? null)}
            className="block w-full text-sm text-text"
          />
        </div>
      </div>
    </Modal>
  );
}
