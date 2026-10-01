import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { listArticles, recordInventoryCounts, type Article, type ArticleCategory } from "../../api/logistics";
import { Modal, NumberField } from "../../design-system";
import { ARTICLE_CATEGORY_OPTIONS } from "./materielLabels";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

const CATEGORY_CHIPS: Array<{ value: ArticleCategory | "all"; label: string }> = [
  { value: "all", label: "Toutes" },
  ...ARTICLE_CATEGORY_OPTIONS.map((option) => ({ value: option.value, label: option.label })),
];

export interface CountModalProps {
  open: boolean;
  inventoryId: number | null;
  quarterLabelDisplay: string;
  onClose: () => void;
  onSaved: (message: string) => void;
}

/** « Saisir le comptage » — fiche `logistique.md` §4.10 (Intendant).
 * Comptage à l'aveugle (point ouvert n° 8) : le stock théorique n'est
 * jamais affiché ici, seulement après l'enregistrement (carte et détail). */
export function CountModal({ open, inventoryId, quarterLabelDisplay, onClose, onSaved }: CountModalProps) {
  const [category, setCategory] = useState<ArticleCategory | "all">("all");
  const [onlyUncounted, setOnlyUncounted] = useState(false);
  const [search, setSearch] = useState("");
  const [values, setValues] = useState<Record<number, number | null>>({});
  const [touched, setTouched] = useState<Set<number>>(new Set());
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  const articlesQuery = useQuery({
    queryKey: ["logistics", "articles", "for-count"],
    queryFn: () => listArticles(),
    enabled: open,
  });

  useEffect(() => {
    if (!open) return;
    setCategory("all");
    setOnlyUncounted(false);
    setSearch("");
    setValues({});
    setTouched(new Set());
    setSubmitError(undefined);
  }, [open]);

  const articles = articlesQuery.data?.results ?? [];
  const filtered = useMemo(() => {
    return articles.filter((article: Article) => {
      if (category !== "all" && article.category !== category) return false;
      if (onlyUncounted && touched.has(article.id)) return false;
      if (search.trim() && !article.name.toLowerCase().includes(search.trim().toLowerCase())) return false;
      return true;
    });
  }, [articles, category, onlyUncounted, search, touched]);

  const countedTotal = touched.size;

  async function handleSubmit(): Promise<void> {
    const counts = [...touched]
      .map((articleId) => ({ article_id: articleId, physical_quantity: values[articleId] }))
      .filter((entry): entry is { article_id: number; physical_quantity: number } => entry.physical_quantity != null);
    if (counts.length === 0) {
      setSubmitError("Saisissez au moins un comptage.");
      return;
    }
    if (inventoryId === null) return;
    setSubmitting(true);
    setSubmitError(undefined);
    try {
      const result = await recordInventoryCounts(inventoryId, counts);
      onSaved(`Comptage enregistré : ${result.lines_counted} article(s). ${result.to_justify} écart(s) à justifier.`);
    } catch (error) {
      setSubmitError(apiErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Comptage · ${quarterLabelDisplay}`}
      size="xl"
      isDirty={touched.size > 0}
      isSubmitting={submitting}
      confirmLabel="Enregistrer le comptage"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-3">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Rechercher un article"
          aria-label="Rechercher un article"
          className="h-control-sm w-full rounded-sm border border-border-strong bg-surface px-3 text-sm text-text placeholder:text-text-muted"
        />
        <div className="flex flex-wrap gap-1">
          {CATEGORY_CHIPS.map((chip) => (
            <button
              key={chip.value}
              type="button"
              onClick={() => setCategory(chip.value)}
              className={[
                "h-control-sm rounded-full border px-3 text-xs font-medium",
                category === chip.value
                  ? "border-primary bg-primary text-on-primary"
                  : "border-border-strong bg-surface text-text",
              ].join(" ")}
            >
              {chip.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setOnlyUncounted((v) => !v)}
            aria-pressed={onlyUncounted}
            className={[
              "h-control-sm rounded-full border px-3 text-xs font-medium",
              onlyUncounted ? "border-primary bg-primary text-on-primary" : "border-border-strong bg-surface text-text",
            ].join(" ")}
          >
            Pas encore comptés
          </button>
        </div>
        <p className="text-xs text-text-muted">
          {countedTotal} sur {articles.length} comptés
        </p>

        {articlesQuery.isLoading ? (
          <p className="text-sm text-text-muted">Chargement…</p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-text-muted">Aucun article ne correspond à ces filtres.</p>
        ) : (
          <ul className="divide-y divide-border">
            {filtered.map((article) => (
              <li key={article.id} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-text">{article.name}</p>
                  <p className="truncate text-xs text-text-muted">
                    {article.category_display} · {article.unit}
                  </p>
                </div>
                <div className="w-32 shrink-0">
                  <NumberField
                    label="Stock compté"
                    value={values[article.id] ?? null}
                    onChange={(value) => {
                      setValues((current) => ({ ...current, [article.id]: value }));
                      setTouched((current) => {
                        const next = new Set(current);
                        if (value === null) next.delete(article.id);
                        else next.add(article.id);
                        return next;
                      });
                    }}
                    min={0}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
