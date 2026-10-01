import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";

/**
 * `ArticleSearch` (fiche `docs/ecrans/logistique.md` §4.8) : variante de
 * `PlayerSearch` (design system §3.4, « variantes du même composant »).
 * Même comportement (combobox ARIA, debounce 250 ms, 8 suggestions, puce de
 * sélection avec « Changer ») ; seule la source change. **Jamais de
 * `<select>` pour choisir un article**, même logique que pour un joueur
 * (CLAUDE.md §2.15 étendu par cohérence de composant).
 */
export interface ArticleSearchResult {
  id: number;
  name: string;
  categoryLabel: string;
  unit: string;
  /** Stock renvoyé par l'API : jamais recalculé ici (§3.1). */
  inStock: number;
}

export type SearchArticles = (query: string) => Promise<ArticleSearchResult[]>;

type SuggestionState = "idle" | "loading" | "error" | "success";

function useArticleSuggestions(
  query: string,
  searchArticles: SearchArticles,
): { results: ArticleSearchResult[]; state: SuggestionState } {
  const debounced = useDebouncedValue(query, 250);
  const [results, setResults] = useState<ArticleSearchResult[]>([]);
  const [state, setState] = useState<SuggestionState>("idle");
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (debounced.trim() === "") {
      setResults([]);
      setState("idle");
      return;
    }
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setState("loading");
    searchArticles(debounced)
      .then((data) => {
        if (requestIdRef.current !== requestId) return;
        setResults(data);
        setState("success");
      })
      .catch(() => {
        if (requestIdRef.current !== requestId) return;
        setResults([]);
        setState("error");
      });
  }, [debounced, searchArticles]);

  return { results, state };
}

export interface ArticleSearchProps {
  value: ArticleSearchResult | null;
  onChange: (article: ArticleSearchResult | null) => void;
  searchArticles: SearchArticles;
  /** « out » grise les articles à stock nul, « Stock épuisé » (§4.8). */
  mode?: "in" | "out";
  /** Articles déjà choisis sur une autre ligne (§4.5 : « n'est plus proposé »). */
  excludeIds?: Set<number>;
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
}

export function ArticleSearch({
  value,
  onChange,
  searchArticles,
  mode = "in",
  excludeIds,
  placeholder = "Nom de l'article",
  disabled,
  ariaLabel = "Nom de l'article",
}: ArticleSearchProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const { results: rawResults, state } = useArticleSuggestions(query, searchArticles);
  const results = excludeIds ? rawResults.filter((a) => !excludeIds.has(a.id)) : rawResults;
  const listboxId = useId();
  const inputId = `${listboxId}-input`;

  useEffect(() => {
    setHighlighted(0);
  }, [results.length, query]);

  function isOutOfStock(article: ArticleSearchResult): boolean {
    return mode === "out" && article.inStock <= 0;
  }

  function selectAt(index: number): void {
    const article = results[index];
    if (!article || isOutOfStock(article)) return;
    onChange(article);
    setQuery("");
    setOpen(false);
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLInputElement>): void {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setHighlighted((h) => Math.min(Math.max(results.length - 1, 0), h + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((h) => Math.max(0, h - 1));
    } else if (event.key === "Enter") {
      if (open) {
        event.preventDefault();
        selectAt(highlighted);
      }
    } else if (event.key === "Escape") {
      if (open) {
        event.stopPropagation();
        setOpen(false);
      }
    }
  }

  if (value) {
    return (
      <div className="flex h-control-md items-center justify-between gap-2 rounded-sm border border-border-strong bg-surface px-3">
        <span className="flex min-w-0 items-center gap-2 text-sm text-text">
          <span className="truncate">{value.name}</span>
          <span className="shrink-0 text-text-muted">En stock : {value.inStock}</span>
        </span>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange(null)}
          className="shrink-0 text-xs font-medium text-primary-text hover:underline disabled:opacity-60"
        >
          Changer
        </button>
      </div>
    );
  }

  const activeOption = results[highlighted];

  return (
    <div className="relative">
      <label className="sr-only" htmlFor={inputId}>
        {ariaLabel}
      </label>
      <div className="relative">
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4.3-4.3" strokeLinecap="round" />
        </svg>
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={
            open && activeOption ? `${listboxId}-option-${activeOption.id}` : undefined
          }
          autoComplete="off"
          disabled={disabled}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="h-control-md w-full rounded-sm border border-border-strong bg-surface pl-8 pr-3 text-base text-text placeholder:text-text-muted disabled:opacity-60"
        />
      </div>
      {open ? (
        <ul
          id={listboxId}
          role="listbox"
          aria-label={ariaLabel}
          className="absolute z-10 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-border bg-surface shadow-elevated"
        >
          {query.trim() === "" ? (
            <li className="px-3 py-2 text-sm text-text-muted">Tapez le nom de l'article.</li>
          ) : state === "loading" ? (
            <li className="px-3 py-2 text-sm text-text-muted">Recherche…</li>
          ) : state === "error" ? (
            <li className="px-3 py-2 text-sm text-status-danger-fg">
              Recherche impossible. Vérifiez votre connexion.
            </li>
          ) : results.length === 0 ? (
            <li className="px-3 py-2 text-sm text-text-muted">
              Aucun article ne correspond à « {query} ».
            </li>
          ) : (
            results.slice(0, 8).map((article, index) => {
              const outOfStock = isOutOfStock(article);
              return (
                <li
                  key={article.id}
                  id={`${listboxId}-option-${article.id}`}
                  role="option"
                  aria-selected={index === highlighted}
                  aria-disabled={outOfStock || undefined}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    selectAt(index);
                  }}
                  onMouseEnter={() => setHighlighted(index)}
                  className={[
                    "flex min-h-14 items-center justify-between gap-2 px-3 py-2",
                    outOfStock ? "cursor-not-allowed opacity-50" : "cursor-pointer",
                    index === highlighted && !outOfStock ? "bg-surface-muted" : "",
                  ].join(" ")}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-text">{article.name}</p>
                    <p className="truncate text-xs text-text-muted">
                      {article.categoryLabel} · {article.unit}
                    </p>
                    {outOfStock ? <p className="text-xs text-status-danger-fg">Stock épuisé</p> : null}
                  </div>
                  {!outOfStock ? (
                    <span className="shrink-0 text-xs text-text-muted">En stock : {article.inStock}</span>
                  ) : null}
                </li>
              );
            })
          )}
        </ul>
      ) : null}
    </div>
  );
}
