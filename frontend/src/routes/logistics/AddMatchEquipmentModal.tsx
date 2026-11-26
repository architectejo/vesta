import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { searchArticles, type MatchEquipmentOutLine } from "../../api/logistics";
import { HolderPicker } from "./HolderPicker";
import { UNLOCATED_LABEL } from "./HolderSearch";
import { ArticleSearch, Button, IconButton, IconRemove, Modal, NumberField, type ArticleSearchResult } from "../../design-system";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

interface Line {
  key: number;
  article: ArticleSearchResult | null;
  quantity: number | null;
  /** Source choisie par « Changer » ; `undefined` = détenteur suggéré par l'API. */
  holderId?: number | null;
  holderChanged: boolean;
  pickerOpen: boolean;
  error?: string;
}

function emptyLine(): Line {
  return { key: nextKey++, article: null, quantity: null, holderChanged: false, pickerOpen: false };
}

let nextKey = 0;

export interface AddMatchEquipmentModalProps {
  open: boolean;
  clubName: string;
  opponent: string;
  eventDate: string;
  onClose: () => void;
  /** `holder_id` n'est présent que si la source a été changée (spec B4 §1.5). */
  onSubmit: (lines: MatchEquipmentOutLine[]) => Promise<void>;
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
  const [lines, setLines] = useState<Line[]>([emptyLine()]);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLines([emptyLine()]);
    setSubmitError(undefined);
  }, [open]);

  function updateLine(key: number, patch: Partial<Line>): void {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch, error: undefined } : line)));
  }

  function removeLine(key: number): void {
    setLines((current) => current.filter((line) => line.key !== key));
  }

  function addLine(): void {
    setLines((current) => [...current, emptyLine()]);
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
        nextLines.map((line) => {
          const entry: MatchEquipmentOutLine = { article_id: Number(line.article!.id), quantity: line.quantity as number };
          const suggestedId = line.article!.suggestedHolder?.id;
          if (line.holderChanged && line.holderId !== undefined && line.holderId !== suggestedId) {
            entry.holder_id = line.holderId;
          }
          return entry;
        }),
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
                  onChange={(article) =>
                    updateLine(line.key, { article, holderId: undefined, holderChanged: false, pickerOpen: false })
                  }
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
              {line.article && (line.article.stockByHolder ?? []).some((row) => row.holder_id !== null) ? (
                line.pickerOpen ? (
                  <HolderPicker
                    label="D'où sort le matériel ?"
                    rows={line.article.stockByHolder ?? []}
                    value={line.holderChanged ? line.holderId : (line.article.suggestedHolder?.id ?? undefined)}
                    onChange={(holderId) => updateLine(line.key, { holderId, holderChanged: true })}
                  />
                ) : (
                  <p className="text-[13px] text-text-muted">
                    Chez {line.article.suggestedHolder?.name ?? UNLOCATED_LABEL} ·{" "}
                    <button
                      type="button"
                      onClick={() => updateLine(line.key, { pickerOpen: true })}
                      className="-my-2 py-2 font-medium text-primary-text hover:underline"
                    >
                      Changer
                    </button>
                  </p>
                )
              ) : null}
            </div>
            {lines.length > 1 ? (
              <IconButton
                aria-label={`Retirer ${line.article?.name ?? "cette ligne"}`}
                variant="secondary"
                onClick={() => removeLine(line.key)}
                icon={<IconRemove aria-hidden="true" className="h-4 w-4" />}
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
