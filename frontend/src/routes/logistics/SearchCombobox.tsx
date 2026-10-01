import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";

/**
 * Combobox de recherche générique, local au module logistique : sert la
 * recherche de match et la recherche de dépense de la modale « Enregistrer
 * un mouvement » (fiche `logistique.md` §4.4, §4.8 — « même combobox »).
 * Comportement aligné sur `ArticleSearch`/`PlayerSearch` (debounce 250 ms,
 * 8 suggestions, puce de sélection avec « Changer »), sans dupliquer un
 * composant de design system pour un usage à deux emplois.
 */
export interface SearchComboboxProps<T extends { id: number | string }> {
  value: T | null;
  onChange: (item: T | null) => void;
  search: (query: string) => Promise<T[]>;
  placeholder: string;
  ariaLabel: string;
  renderOption: (item: T) => ReactNode;
  renderSelected: (item: T) => ReactNode;
  emptyHint?: string;
  disabled?: boolean;
  /** Message affiché à la place du champ (accès refusé, ex. Intendant / dépenses). */
  unavailableMessage?: string;
}

export function SearchCombobox<T extends { id: number | string }>({
  value,
  onChange,
  search,
  placeholder,
  ariaLabel,
  renderOption,
  renderSelected,
  emptyHint = "Tapez pour rechercher.",
  disabled,
  unavailableMessage,
}: SearchComboboxProps<T>) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<T[]>([]);
  const [state, setState] = useState<"idle" | "loading" | "error" | "success">("idle");
  const debounced = useDebouncedValue(query, 250);
  const requestIdRef = useRef(0);
  const listboxId = useId();

  useEffect(() => {
    if (unavailableMessage) return;
    if (debounced.trim() === "") {
      setResults([]);
      setState("idle");
      return;
    }
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setState("loading");
    search(debounced)
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
  }, [debounced, search, unavailableMessage]);

  if (unavailableMessage) {
    return <p className="text-xs text-text-muted">{unavailableMessage}</p>;
  }

  if (value) {
    return (
      <div className="flex h-control-md items-center justify-between gap-2 rounded-sm border border-border-strong bg-surface px-3">
        <span className="min-w-0 flex-1 truncate text-sm text-text">{renderSelected(value)}</span>
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

  return (
    <div className="relative">
      <label className="sr-only" htmlFor={listboxId}>
        {ariaLabel}
      </label>
      <input
        id={listboxId}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={`${listboxId}-list`}
        aria-autocomplete="list"
        autoComplete="off"
        disabled={disabled}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        placeholder={placeholder}
        className="h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text placeholder:text-text-muted disabled:opacity-60"
      />
      {open ? (
        <ul
          id={`${listboxId}-list`}
          role="listbox"
          aria-label={ariaLabel}
          className="absolute z-10 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-border bg-surface shadow-elevated"
        >
          {query.trim() === "" ? (
            <li className="px-3 py-2 text-sm text-text-muted">{emptyHint}</li>
          ) : state === "loading" ? (
            <li className="px-3 py-2 text-sm text-text-muted">Recherche…</li>
          ) : state === "error" ? (
            <li className="px-3 py-2 text-sm text-status-danger-fg">
              Recherche impossible. Vérifiez votre connexion.
            </li>
          ) : results.length === 0 ? (
            <li className="px-3 py-2 text-sm text-text-muted">Aucun résultat pour « {query} ».</li>
          ) : (
            results.slice(0, 8).map((item) => (
              <li
                key={item.id}
                role="option"
                aria-selected={false}
                onMouseDown={(e) => {
                  e.preventDefault();
                  onChange(item);
                  setQuery("");
                  setOpen(false);
                }}
                className="min-h-14 cursor-pointer px-3 py-2 hover:bg-surface-muted"
              >
                {renderOption(item)}
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
