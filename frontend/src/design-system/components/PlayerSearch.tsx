import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { IconRemove, IconSearch } from "../icons";
import { Avatar } from "./Avatar";
import { StatusBadge } from "./StatusBadge";
import type { StatusKey } from "./statusMap";

export interface PlayerSearchResult {
  id: string | number;
  firstName: string;
  lastName: string;
  number?: number | null;
  position?: string | null;
  photoUrl?: string | null;
  status?: { key: StatusKey; detail?: string };
  /** Fourni par l'API : jamais évalué par l'interface (3.4). */
  eligible?: boolean;
  /** Raison de l'inéligibilité, fournie par l'API (ex. « En dette : 20 $ »). */
  ineligibleReason?: string;
}

export type SearchPlayers = (query: string) => Promise<PlayerSearchResult[]>;

type SuggestionState = "idle" | "loading" | "error" | "success";

function usePlayerSuggestions(
  query: string,
  searchPlayers: SearchPlayers,
): { results: PlayerSearchResult[]; state: SuggestionState } {
  const debounced = useDebouncedValue(query, 250);
  const [results, setResults] = useState<PlayerSearchResult[]>([]);
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
    searchPlayers(debounced)
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
  }, [debounced, searchPlayers]);

  return { results, state };
}

function playerFullName(player: PlayerSearchResult): string {
  return `${player.firstName} ${player.lastName}`;
}

interface PlayerComboboxFieldProps {
  query: string;
  onQueryChange: (query: string) => void;
  onSelect: (player: PlayerSearchResult) => void;
  searchPlayers: SearchPlayers;
  placeholder: string;
  renderMeta?: (player: PlayerSearchResult) => ReactNode;
  excludeIds?: Set<string | number>;
  disabled?: boolean;
  ariaLabel: string;
}

/** Cœur du composant (3.4) : champ + liste de suggestions ARIA combobox. */
function PlayerComboboxField({
  query,
  onQueryChange,
  onSelect,
  searchPlayers,
  placeholder,
  renderMeta,
  excludeIds,
  disabled,
  ariaLabel,
}: PlayerComboboxFieldProps) {
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const { results: rawResults, state } = usePlayerSuggestions(query, searchPlayers);
  const results = excludeIds ? rawResults.filter((p) => !excludeIds.has(p.id)) : rawResults;
  const listboxId = useId();
  const inputId = `${listboxId}-input`;

  useEffect(() => {
    setHighlighted(0);
  }, [results.length, query]);

  function selectAt(index: number): void {
    const player = results[index];
    if (!player || player.eligible === false) return;
    onSelect(player);
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
          aria-activedescendant={
            open && activeOption ? `${listboxId}-option-${activeOption.id}` : undefined
          }
          autoComplete="off"
          disabled={disabled}
          value={query}
          onChange={(e) => {
            onQueryChange(e.target.value);
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
            <li className="px-3 py-2 text-sm text-text-muted">Tapez un nom ou un numéro.</li>
          ) : state === "loading" ? (
            <li className="px-3 py-2 text-sm text-text-muted">Recherche…</li>
          ) : state === "error" ? (
            <li className="px-3 py-2 text-sm text-status-danger-fg">
              Recherche impossible. Vérifiez votre connexion.
            </li>
          ) : results.length === 0 ? (
            <li className="px-3 py-2 text-sm text-text-muted">
              Aucun joueur ne correspond à « {query} ».
            </li>
          ) : (
            results.slice(0, 8).map((player, index) => {
              const ineligible = player.eligible === false;
              return (
                <li
                  key={player.id}
                  id={`${listboxId}-option-${player.id}`}
                  role="option"
                  aria-selected={index === highlighted}
                  aria-disabled={ineligible || undefined}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    selectAt(index);
                  }}
                  onMouseEnter={() => setHighlighted(index)}
                  className={[
                    "flex min-h-14 items-center gap-2 px-3 py-2",
                    ineligible ? "cursor-not-allowed opacity-50" : "cursor-pointer",
                    index === highlighted && !ineligible ? "bg-surface-muted" : "",
                  ].join(" ")}
                >
                  <Avatar name={playerFullName(player)} photoUrl={player.photoUrl} size={40} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-text">{playerFullName(player)}</p>
                    <p className="truncate text-xs text-text-muted">
                      {[player.number != null ? `n° ${player.number}` : null, player.position]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    {player.status ? (
                      <StatusBadge status={player.status.key} detail={player.status.detail} />
                    ) : null}
                    {ineligible && player.ineligibleReason ? (
                      <p className="text-xs text-status-danger-fg">{player.ineligibleReason}</p>
                    ) : null}
                  </div>
                  {!ineligible && renderMeta ? (
                    <div className="shrink-0 text-xs text-text-muted">{renderMeta(player)}</div>
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

export interface PlayerSearchProps {
  value: PlayerSearchResult | null;
  onChange: (player: PlayerSearchResult | null) => void;
  searchPlayers: SearchPlayers;
  placeholder?: string;
  renderMeta?: (player: PlayerSearchResult) => ReactNode;
  disabled?: boolean;
  ariaLabel?: string;
}

/**
 * Seul moyen de choisir un joueur (docs/lot0/design-system.md §3.4).
 * **Jamais** de `<select>` de joueurs dans Vesta (CLAUDE.md §2.15).
 */
export function PlayerSearch({
  value,
  onChange,
  searchPlayers,
  placeholder = "Nom ou numéro du joueur",
  renderMeta,
  disabled,
  ariaLabel = "Nom ou numéro du joueur",
}: PlayerSearchProps) {
  const [query, setQuery] = useState("");

  if (value) {
    return (
      <div className="flex h-control-md items-center justify-between gap-2 rounded-sm border border-border-strong bg-surface px-3">
        <span className="flex min-w-0 items-center gap-2 text-sm text-text">
          <Avatar name={playerFullName(value)} photoUrl={value.photoUrl} size={24} />
          <span className="truncate">{playerFullName(value)}</span>
          {value.number != null ? (
            <span className="shrink-0 text-text-muted">n° {value.number}</span>
          ) : null}
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

  return (
    <PlayerComboboxField
      query={query}
      onQueryChange={setQuery}
      onSelect={(player) => {
        onChange(player);
        setQuery("");
      }}
      searchPlayers={searchPlayers}
      placeholder={placeholder}
      renderMeta={renderMeta}
      disabled={disabled}
      ariaLabel={ariaLabel}
    />
  );
}

export interface PlayerMultiSearchProps {
  values: PlayerSearchResult[];
  onChange: (players: PlayerSearchResult[]) => void;
  searchPlayers: SearchPlayers;
  placeholder?: string;
  renderMeta?: (player: PlayerSearchResult) => ReactNode;
  disabled?: boolean;
  ariaLabel?: string;
}

/** Sélection multiple : puces sous le champ, chacune retirable (3.4). */
export function PlayerMultiSearch({
  values,
  onChange,
  searchPlayers,
  placeholder = "Nom ou numéro du joueur",
  renderMeta,
  disabled,
  ariaLabel = "Nom ou numéro du joueur",
}: PlayerMultiSearchProps) {
  const [query, setQuery] = useState("");
  const excludeIds = new Set(values.map((v) => v.id));

  return (
    <div>
      <PlayerComboboxField
        query={query}
        onQueryChange={setQuery}
        onSelect={(player) => {
          onChange([...values, player]);
          setQuery("");
        }}
        searchPlayers={searchPlayers}
        placeholder={placeholder}
        renderMeta={renderMeta}
        excludeIds={excludeIds}
        disabled={disabled}
        ariaLabel={ariaLabel}
      />
      {values.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-2">
          {values.map((player) => (
            <li
              key={player.id}
              className="flex items-center gap-2 rounded-full bg-surface-muted py-1 pl-1 pr-2 text-sm text-text"
            >
              <Avatar name={playerFullName(player)} photoUrl={player.photoUrl} size={24} />
              <span>{playerFullName(player)}</span>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChange(values.filter((v) => v.id !== player.id))}
                aria-label={`Retirer ${playerFullName(player)}`}
                className="text-text-muted hover:text-text disabled:opacity-60"
              >
                <IconRemove aria-hidden="true" className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
