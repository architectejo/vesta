import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import type { Article, ArticleCategory, ArticleCondition, ArticleInput } from "../../api/logistics";
import { Modal, SegmentedControl, TextField } from "../../design-system";
import { ARTICLE_CATEGORY_OPTIONS, ARTICLE_CONDITION_OPTIONS } from "./materielLabels";

export interface ArticleFormModalProps {
  open: boolean;
  /** Présent = modification ; absent = création (fiche §4.2). */
  article?: Article | null;
  onClose: () => void;
  onSubmit: (input: ArticleInput) => Promise<void>;
}

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

/** « Ajouter un article » / « Modifier l'article » (fiche `logistique.md` §4.2). */
export function ArticleFormModal({ open, article, onClose, onSubmit }: ArticleFormModalProps) {
  const isEdit = Boolean(article);
  const [name, setName] = useState(article?.name ?? "");
  const [category, setCategory] = useState<ArticleCategory | null>(article?.category ?? null);
  const [unit, setUnit] = useState(article?.unit ?? "pièce");
  const [condition, setCondition] = useState<ArticleCondition>(article?.reference_condition ?? "new");
  const [nameError, setNameError] = useState<string | undefined>(undefined);
  const [categoryError, setCategoryError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(article?.name ?? "");
    setCategory(article?.category ?? null);
    setUnit(article?.unit ?? "pièce");
    setCondition(article?.reference_condition ?? "new");
    setNameError(undefined);
    setCategoryError(undefined);
    setSubmitError(undefined);
  }, [open, article]);

  async function handleSubmit(): Promise<void> {
    let hasError = false;
    if (!name.trim()) {
      setNameError("Ce champ est obligatoire.");
      hasError = true;
    } else {
      setNameError(undefined);
    }
    if (!category) {
      setCategoryError("Choisissez une catégorie.");
      hasError = true;
    } else {
      setCategoryError(undefined);
    }
    if (hasError || !category) return;

    setSubmitting(true);
    setSubmitError(undefined);
    try {
      await onSubmit({ name: name.trim(), category, unit: unit.trim() || "pièce", reference_condition: condition });
    } catch (error) {
      setSubmitError(apiErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  const isDirty =
    name.trim() !== (article?.name ?? "") ||
    category !== (article?.category ?? null) ||
    unit.trim() !== (article?.unit ?? "pièce") ||
    condition !== (article?.reference_condition ?? "new");

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? "Modifier l'article" : "Ajouter un article"}
      size="md"
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <TextField label="Nom" value={name} onChange={setName} maxLength={120} error={nameError} />
        {/* 10 catégories : `<select>` natif permis (ce n'est pas un joueur,
            spec intendance §8) ; un SegmentedControl ne tient pas à 360 px. */}
        <label className="block text-sm font-medium text-text">
          Catégorie
          <select
            value={category ?? ""}
            onChange={(e) => setCategory(e.target.value ? (e.target.value as ArticleCategory) : null)}
            aria-invalid={categoryError ? true : undefined}
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text"
          >
            <option value="">Choisissez une catégorie</option>
            {ARTICLE_CATEGORY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {categoryError ? <p className="mt-1 text-xs text-status-danger-fg">{categoryError}</p> : null}
        </label>
        <TextField
          label="Unité"
          value={unit}
          onChange={setUnit}
          maxLength={20}
          help="Par exemple : pièce, paire, lot."
        />
        <SegmentedControl
          label="État"
          value={condition}
          onChange={setCondition}
          options={ARTICLE_CONDITION_OPTIONS}
          wrapOnMobile
        />
        {!isEdit ? (
          <p className="text-xs text-text-muted">
            Le stock démarre à 0. Enregistrez ensuite une entrée (achat, dotation) pour indiquer les quantités.
          </p>
        ) : null}
        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
