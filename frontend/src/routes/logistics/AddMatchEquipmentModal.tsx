import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { searchArticles } from "../../api/logistics";
import { ArticleSearch, Button, IconButton, Modal, NumberField, type ArticleSearchResult } from "../../design-system";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

interface Line {
  key: number;
  article: ArticleSearchResult | null;
  quantity: number | null;
  error?: string;
}

let nextKey = 0;

export interface AddMatchEquipmentModalProps {
  open: boolean;
  clubName: string;
  opponent: string;
  eventDate: string;
  onClose: () => void;
  onSubmit: (lines: Array<{ article_id: number; quantity: number }>) => Promise<void>;
}

/** « Ajouter des équipements » (feuille de match) — fiche `logistique.md`
 * §4.5. Enregistrement « tout ou rien » (point ouvert n° 10) : géré par
 * `recordMatchEquipmentOut` côté API, jamais recalculé ici. */
export function AddMatchEquipmentModal({
  open,
  clubName,
  opponent,
  eventDate,
  onClose,
  onSubmit,
}: AddMatchEquipmentModalProps) {
  const [lines, setLines] = useState<Line[]>([{ key: nextKey++, article: null, quantity: null }]);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLines([{ key: nextKey++, article: null, quantity: null }]);
    setSubmitError(undefined);
  }, [open]);

  function updateLine(key: number, patch: Partial<Line>): void {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch, error: undefined } : line)));
  }

  function removeLine(key: number): void {
    setLines((current) => current.filter((line) => line.key !== key));
  }

  function addLine(): void {
    setLines((current) => [...current, { key: nextKey++, article: null, quantity: null }]);
  }

  const excludeIds = new Set(lines.map((line) => line.article?.id).filter((id): id is number => id != null));

  async function handleSubmit(): Promise<void> {
    let hasError = false;
    const nextLines = lines.map((line) => {
      if (!line.article) {
        hasError = true;
        return { ...line, error: "Choisissez un article." };
      }
      if (!line.quantity || line.quantity < 1) {
        hasError = true;
        return { ...line, error: "Saisissez une quantité supérieure à 0." };
      }
      return { ...line, error: undefined };
    });
    setLines(nextLines);
    if (hasError) return;

    setSubmitting(true);
    setSubmitError(undefined);
    try {
      await onSubmit(
        nextLines.map((line) => ({ article_id: Number(line.article!.id), quantity: line.quantity as number })),
      );
    } catch (error) {
      setSubmitError(apiErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  const isDirty = lines.some((line) => line.article || line.quantity);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Ajouter des équipements"
      subtitle={`${clubName} – ${opponent}${eventDate ? ` · ${eventDate}` : ""}`}
      size="md"
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        {lines.map((line) => (
          <div key={line.key} className="flex items-end gap-2 rounded-md border border-border p-2">
            <div className="min-w-0 flex-1 space-y-2">
              <div>
                <p className="mb-1 text-sm font-medium text-text">Article</p>
                <ArticleSearch
                  value={line.article}
                  onChange={(article) => updateLine(line.key, { article })}
                  searchArticles={searchArticles}
                  mode="out"
                  excludeIds={excludeIds}
                />
              </div>
              <NumberField
                label="Quantité"
                value={line.quantity}
                onChange={(quantity) => updateLine(line.key, { quantity })}
                min={1}
                error={line.error}
              />
            </div>
            {lines.length > 1 ? (
              <IconButton
                aria-label={`Retirer ${line.article?.name ?? "cette ligne"}`}
                variant="secondary"
                onClick={() => removeLine(line.key)}
                icon={
                  <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                  </svg>
                }
              />
            ) : null}
          </div>
        ))}
        <Button variant="ghost" size="sm" onClick={addLine}>
          Ajouter une ligne
        </Button>
        <p className="text-xs text-text-muted">
          Chaque équipement crée une sortie « Prêt pour un match » dans le registre du matériel. Enregistrez le retour
          après le match.
        </p>
        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
