import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { IconSearch } from "../icons";
import { Avatar } from "./Avatar";

/**
 * `ClubSearch` (fiche `docs/ecrans/mercato.md`, composants §0) : combobox de
 * recherche d'un club Vesta (autre que le nôtre), même comportement que
 * `PlayerSearch`/`ArticleSearch` (debounce 250 ms, 8 suggestions, puce de
 * sélection avec « Changer »). **Jamais de `<select>`** (même logique que
 * pour un joueur ou un article).
 */
export interface ClubSearchResult {
  id: number;
  name: string;
  logo?: string | null;
  city?: string;
}

export type SearchClubs = (query: string) => Promise<ClubSearchResult[]>;

type SuggestionState = "idle" | "loading" | "error" | "success";

function useClubSuggestions(
  query: string,
  searchClubs: SearchClubs,
): { results: ClubSearchResult[]; state: SuggestionState } {
  const debounced = useDebouncedValue(query, 250);
  const [results, setResults] = useState<ClubSearchResult[]>([]);
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
    searchClubs(debounced)
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
  }, [debounced, searchClubs]);

  return { results, state };
}

export interface ClubSearchProps {
  value: ClubSearchResult | null;
  onChange: (club: ClubSearchResult | null) => void;
  searchClubs: SearchClubs;
  placeholder?: string;
  disabled?: boolean;
  error?: string;
  ariaLabel?: string;
}

export function ClubSearch({
  value,
  onChange,
  searchClubs,
  placeholder = "Nom du club",
  disabled,
  error,
  ariaLabel = "Nom du club",
}: ClubSearchProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const { results, state } = useClubSuggestions(query, searchClubs);
  const listboxId = useId();
  const inputId = `${listboxId}-input`;

  useEffect(() => {
    setHighlighted(0);
  }, [results.length, query]);

  function selectAt(index: number): void {
    const club = results[index];
    if (!club) return;
    onChange(club);
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
          <Avatar name={value.name} photoUrl={value.logo} size={24} />
          <span className="truncate">{value.name}</span>
        </span>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange(null)}
          className="inline-flex min-h-control-sm items-center shrink-0 text-xs font-medium text-primary-text hover:underline disabled:opacity-60"
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
        <IconSearch
          aria-hidden="true"
          className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
        />
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-invalid={Boolean(error) || undefined}
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
          className={[
            "h-control-md w-full rounded-sm border bg-surface pl-8 pr-3 text-base text-text placeholder:text-text-muted disabled:opacity-60",
            error ? "border-status-danger-fg" : "border-border-strong",
          ].join(" ")}
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
            <li className="px-3 py-2 text-sm text-text-muted">Tapez le nom d'un club.</li>
          ) : state === "loading" ? (
            <li className="px-3 py-2 text-sm text-text-muted">Recherche…</li>
          ) : state === "error" ? (
            <li className="px-3 py-2 text-sm text-status-danger-fg">
              Recherche impossible. Vérifiez votre connexion.
            </li>
          ) : results.length === 0 ? (
            <li className="px-3 py-2 text-sm text-text-muted">
              Aucun club ne correspond à « {query} ».
            </li>
          ) : (
            results.slice(0, 8).map((club, index) => (
              <li
                key={club.id}
                id={`${listboxId}-option-${club.id}`}
                role="option"
                aria-selected={index === highlighted}
                onMouseDown={(e) => {
                  e.preventDefault();
                  selectAt(index);
                }}
                onMouseEnter={() => setHighlighted(index)}
                className={[
                  "flex min-h-14 cursor-pointer items-center gap-2 px-3 py-2",
                  index === highlighted ? "bg-surface-muted" : "",
                ].join(" ")}
              >
                <Avatar name={club.name} photoUrl={club.logo} size={32} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-text">{club.name}</p>
                  {club.city ? <p className="truncate text-xs text-text-muted">{club.city}</p> : null}
                </div>
              </li>
            ))
          )}
        </ul>
      ) : null}
      {error ? <p className="mt-1 text-xs text-status-danger-fg">{error}</p> : null}
    </div>
  );
}
