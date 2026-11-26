import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { flagDecommission, searchArticles, type DecommissionReason } from "../../api/logistics";
import {
  ArticleSearch,
  Modal,
  NumberField,
  SegmentedControl,
  TextArea,
  type ArticleSearchResult,
} from "../../design-system";
import { todayIsoDate } from "./format";
import { HolderPicker } from "./HolderPicker";
import { DECOMMISSION_REASON_OPTIONS } from "./materielLabels";
import { OFFLINE_ACTION_MESSAGE, useOnlineStatus } from "./useOnlineStatus";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

type FieldKey = "article" | "holder" | "quantity" | "reason" | "note" | "date" | "submit";

export interface DecommissionFlagModalProps {
  open: boolean;
  level?: 1 | 2;
  /** Article verrouillé (depuis la modale Article). */
  lockedArticle?: ArticleSearchResult | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}

/** « Signaler à déclasser » (spec B4 §3.2), Intendant. */
export function DecommissionFlagModal({ open, level = 1, lockedArticle, onClose, onSaved }: DecommissionFlagModalProps) {
  const [article, setArticle] = useState<ArticleSearchResult | null>(null);
  const [holder, setHolder] = useState<number | null | undefined>(undefined);
  const [quantity, setQuantity] = useState<number | null>(null);
  const [reason, setReason] = useState<DecommissionReason | null>(null);
  const [note, setNote] = useState("");
  const [notedOn, setNotedOn] = useState(todayIsoDate());
  const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [submitting, setSubmitting] = useState(false);
  const online = useOnlineStatus();

  useEffect(() => {
    if (!open) return;
    setArticle(lockedArticle ?? null);
    setHolder(undefined);
    setQuantity(null);
    setReason(null);
    setNote("");
    setNotedOn(todayIsoDate());
    setErrors({});
  }, [open, lockedArticle]);

  const rows = article?.stockByHolder ?? [];
  const showHolder = rows.some((row) => row.holder_id !== null);

  async function handleSubmit(): Promise<void> {
    if (!online) return;
    const next: Partial<Record<FieldKey, string>> = {};
    if (!article) next.article = "Choisissez un article.";
    if (showHolder && holder === undefined) next.holder = "Choisissez chez qui se trouvent les pièces.";
    if (!quantity || quantity < 1) next.quantity = "Saisissez une quantité supérieure à 0.";
    if (!reason) next.reason = "Choisissez le motif.";
    if (reason === "other" && !note.trim()) next.note = "Précisez le motif.";
    if (!notedOn) next.date = "La date du constat est obligatoire.";
    else if (notedOn > todayIsoDate()) next.date = "La date ne peut pas être dans le futur.";
    setErrors(next);
    if (Object.keys(next).length > 0 || !article || !quantity || !reason) return;

    setSubmitting(true);
    try {
      await flagDecommission({
        article_id: Number(article.id),
        ...(showHolder && holder !== undefined ? { holder_id: holder } : {}),
        quantity,
        reason,
        reason_note: note.trim() || undefined,
        noted_on: notedOn,
      });
      onSaved(`${quantity} ${article.unit} de ${article.name} à déclasser.`);
    } catch (error) {
      const message = apiErrorMessage(error);
      if (/article/i.test(message)) setErrors({ article: message });
      else if (/il ne reste|quantit/i.test(message)) setErrors({ quantity: message });
      else if (/date/i.test(message)) setErrors({ date: message });
      else if (/motif/i.test(message)) setErrors({ note: message });
      else if (/détenteur/i.test(message)) setErrors({ holder: message });
      else setErrors({ submit: message });
    } finally {
      setSubmitting(false);
    }
  }

  const isDirty = Boolean((!lockedArticle && article) || quantity || reason || note.trim());

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Signaler à déclasser"
      size="md"
      level={level}
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Signaler"
      confirmLoadingLabel="Enregistrement…"
      confirmDisabled={!online}
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <p className="text-sm text-text-muted">Les pièces restent dans le stock jusqu'à leur sortie.</p>
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
                setHolder(undefined);
                // Pas de « Choisissez un article. » sous un article choisi.
                if (next) setErrors((current) => ({ ...current, article: undefined, holder: undefined }));
              }}
              searchArticles={searchArticles}
              mode="out"
            />
          )}
          {errors.article ? <p className="mt-1 text-xs text-status-danger-fg">{errors.article}</p> : null}
        </div>
        {showHolder ? (
          <HolderPicker label="Chez" rows={rows} value={holder} onChange={setHolder} error={errors.holder} />
        ) : null}
        <NumberField
          label={article ? `Quantité (${article.unit})` : "Quantité"}
          value={quantity}
          onChange={setQuantity}
          min={1}
          error={errors.quantity}
        />
        <SegmentedControl
          label="Motif"
          value={reason}
          onChange={setReason}
          options={DECOMMISSION_REASON_OPTIONS}
          error={errors.reason}
          wrapOnMobile
        />
        <TextArea
          label="Précision"
          optional={reason !== "other"}
          value={note}
          onChange={setNote}
          maxLength={500}
          error={errors.note}
        />
        <label className="block text-sm font-medium text-text">
          Date du constat
          <input
            type="date"
            value={notedOn}
            max={todayIsoDate()}
            onChange={(e) => setNotedOn(e.target.value)}
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
          />
          {errors.date ? <p className="mt-1 text-xs text-status-danger-fg">{errors.date}</p> : null}
        </label>
        {errors.submit ? <p className="text-sm text-status-danger-fg">{errors.submit}</p> : null}
        {!online ? <p className="text-sm text-text-muted">{OFFLINE_ACTION_MESSAGE}</p> : null}
      </div>
    </Modal>
  );
}
