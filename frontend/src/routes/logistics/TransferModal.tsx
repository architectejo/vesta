import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { createTransfer, searchArticles } from "../../api/logistics";
import { ArticleSearch, Modal, NumberField, TextArea, type ArticleSearchResult } from "../../design-system";
import { todayIsoDate } from "./format";
import { HolderPicker } from "./HolderPicker";
import { HolderSearch, UNLOCATED_LABEL, type HolderSelection } from "./HolderSearch";
import { OFFLINE_ACTION_MESSAGE, useOnlineStatus } from "./useOnlineStatus";
import { formatQuantity } from "./materielLabels";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

export interface TransferModalProps {
  open: boolean;
  level?: 1 | 2;
  /** Article prérempli et verrouillé (depuis la modale Article). */
  lockedArticle?: ArticleSearchResult | null;
  /** Source préremplie : id du détenteur, `null` = Non localisé, `undefined` = aucune. */
  initialFrom?: number | null;
  /** Nom de la source préremplie, affiché tant qu'aucun article n'est choisi. */
  initialFromName?: string;
  onClose: () => void;
  onSaved: (message: string) => void;
}

/** « Déplacer du matériel » (spec B4 §1.4), Intendant. */
export function TransferModal({ open, level = 1, lockedArticle, initialFrom, initialFromName, onClose, onSaved }: TransferModalProps) {
  const [article, setArticle] = useState<ArticleSearchResult | null>(null);
  const [from, setFrom] = useState<number | null | undefined>(undefined);
  const [to, setTo] = useState<HolderSelection | null>(null);
  const [quantity, setQuantity] = useState<number | null>(null);
  const [date, setDate] = useState(todayIsoDate());
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<Partial<Record<"article" | "from" | "to" | "quantity" | "date" | "submit", string>>>(
    {},
  );
  const [submitting, setSubmitting] = useState(false);
  const online = useOnlineStatus();

  useEffect(() => {
    if (!open) return;
    setArticle(lockedArticle ?? null);
    setFrom(initialFrom);
    setTo(null);
    setQuantity(null);
    setDate(todayIsoDate());
    setReason("");
    setErrors({});
  }, [open, lockedArticle, initialFrom]);

  const rows = article?.stockByHolder ?? [];
  const sourceRow = from === undefined ? undefined : rows.find((row) => row.holder_id === from);
  const maxQuantity = sourceRow?.quantity;

  async function handleSubmit(): Promise<void> {
    if (!online) return;
    const next: typeof errors = {};
    const today = todayIsoDate();
    if (!article) next.article = "Choisissez un article.";
    if (from === undefined) next.from = "Choisissez d'où vient le matériel.";
    if (!to) next.to = "Choisissez le nouveau détenteur.";
    else if (from !== undefined && to.id === from)
      next.to = "Le détenteur d'arrivée doit être différent du détenteur de départ.";
    if (!quantity || quantity < 1) next.quantity = "Saisissez une quantité supérieure à 0.";
    // Pas de plafonnement silencieux du champ : la quantité saisie n'est
    // jamais remplacée par le stock de la source (spec §4.3, message de l'API).
    else if (sourceRow && quantity > sourceRow.quantity)
      next.quantity = `Quantité supérieure au stock de ${sourceRow.holder_name} (${sourceRow.quantity}).`;
    if (!date) next.date = "La date est obligatoire.";
    else if (date > today) next.date = "La date ne peut pas être dans le futur.";
    setErrors(next);
    if (Object.keys(next).length > 0 || !article || from === undefined || !to || !quantity) return;

    setSubmitting(true);
    try {
      await createTransfer({
        article_id: Number(article.id),
        from_holder_id: from,
        to_holder_id: to.id,
        quantity,
        movement_date: date,
        reason: reason.trim() || undefined,
      });
      onSaved(`Matériel déplacé : ${formatQuantity(quantity, article.unit)} de ${article.name} chez ${to.name}.`);
    } catch (error) {
      const message = apiErrorMessage(error);
      // Routage des erreurs de l'API vers le champ concerné (spec §1.4).
      if (/quantit/i.test(message)) setErrors({ quantity: message });
      else if (/date/i.test(message)) setErrors({ date: message });
      else if (/détenteur|joueur/i.test(message)) setErrors({ to: message });
      else setErrors({ submit: message });
    } finally {
      setSubmitting(false);
    }
  }

  const isDirty = Boolean((!lockedArticle && article) || to || quantity || reason.trim());

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Déplacer du matériel"
      size="md"
      level={level}
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Déplacer"
      confirmLoadingLabel="Déplacement…"
      confirmDisabled={!online}
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <div>
          <p className="mb-1 text-sm font-medium text-text">Article</p>
          {lockedArticle ? (
            <div className="flex h-control-md items-center rounded-sm border border-border-strong bg-surface-muted px-3 text-sm text-text">
              {lockedArticle.name}
            </div>
          ) : (
            <ArticleSearch
              value={article}
              onChange={(next) => {
                setArticle(next);
                // Pas de « Choisissez un article. » sous un article choisi.
                if (next) setErrors((current) => ({ ...current, article: undefined }));
                // La source préremplie reste valable seulement si l'article la contient.
                if (next && from !== undefined && !(next.stockByHolder ?? []).some((r) => r.holder_id === from)) {
                  setFrom(undefined);
                }
              }}
              searchArticles={searchArticles}
              mode="out"
            />
          )}
          {errors.article ? <p className="mt-1 text-xs text-status-danger-fg">{errors.article}</p> : null}
        </div>
        {article ? (
          rows.length > 0 ? (
            <HolderPicker label="De" rows={rows} value={from} onChange={setFrom} error={errors.from} />
          ) : (
            <p className="text-sm text-text-muted">Cet article n'a aucun stock à déplacer.</p>
          )
        ) : from !== undefined ? (
          <p className="text-sm text-text">
            De : <span className="font-medium">{from === null ? UNLOCATED_LABEL : initialFromName ?? ""}</span>
          </p>
        ) : null}
        <div>
          <p className="mb-1 text-sm font-medium text-text">Vers</p>
          <HolderSearch value={to} onChange={setTo} canCreate ariaLabel="Nouveau détenteur" />
          {errors.to ? <p className="mt-1 text-xs text-status-danger-fg">{errors.to}</p> : null}
        </div>
        <NumberField
          label={article ? `Quantité (${article.unit})` : "Quantité"}
          value={quantity}
          onChange={setQuantity}
          min={1}
          help={maxQuantity !== undefined ? `Stock de la source : ${maxQuantity}` : undefined}
          error={errors.quantity}
        />
        <label className="block text-sm font-medium text-text">
          Date
          <input
            type="date"
            value={date}
            max={todayIsoDate()}
            onChange={(e) => setDate(e.target.value)}
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
          />
          {errors.date ? <p className="mt-1 text-xs text-status-danger-fg">{errors.date}</p> : null}
        </label>
        <TextArea label="Motif" optional value={reason} onChange={setReason} maxLength={500} />
        {errors.submit ? <p className="text-sm text-status-danger-fg">{errors.submit}</p> : null}
        {!online ? <p className="text-sm text-text-muted">{OFFLINE_ACTION_MESSAGE}</p> : null}
      </div>
    </Modal>
  );
}
