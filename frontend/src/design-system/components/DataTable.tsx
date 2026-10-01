import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import { Skeleton } from "./Skeleton";

export interface DataTableColumn<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  align?: "left" | "right";
  /** Largeur fixe en px (obligatoire pour une colonne figée, 3.3). */
  widthPx?: number;
  /** Rend l'en-tête cliquable pour trier (tri local, cas non-serveur). */
  sortAccessor?: (row: T) => string | number;
}

export interface FilterChip {
  label: string;
  onRemove: () => void;
}

export interface DataTableProps<T> {
  columns: Array<DataTableColumn<T>>;
  rows: T[];
  getRowId: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  loading?: boolean;
  /** Active la recherche locale ; texte utilisé pour filtrer chaque ligne. */
  getSearchableText?: (row: T) => string;
  searchPlaceholder?: string;
  /** Nom pluriel affiché dans « {n} {resultLabel} » (ex. « joueurs »). */
  resultLabel?: string;
  /** Emplacement pour un bouton « Filtres » propre à l'écran appelant. */
  filtersSlot?: ReactNode;
  activeFilterChips?: FilterChip[];
  onClearFilters?: () => void;
  exportLabel?: string;
  onExport?: () => void;
  pageSize?: number;
  /** Fige la première colonne (3.3), avec `widthPx` défini dessus. */
  stickyFirstColumn?: boolean;
  /** Variante grille des cotisations (4.4.7) : cellules plus compactes. */
  variant?: "table" | "grid";
  /**
   * Défilement horizontal automatique, au premier chargement des lignes,
   * pour amener cette colonne dans le cadre visible (3.3 : mois courant de
   * la grille des cotisations). Ignoré si la colonne n'a pas de `widthPx`.
   */
  scrollToColumnKey?: string;
  /** État vide sans recherche ni filtre (personnalisable par l'écran). */
  emptyState?: ReactNode;
  className?: string;
  /**
   * Classes ajoutées au cadre défilant (celui qui porte `overflow-x-auto`) :
   * utilisé par la grille des cotisations pour plafonner sa hauteur et
   * ajouter le défilement vertical à l'intérieur du cadre, sans faire
   * défiler toute la page (3.3, mobile 360 px).
   */
  scrollAreaClassName?: string;
}

const DEFAULT_PAGE_SIZE = 20;

export function DataTable<T>({
  columns,
  rows,
  getRowId,
  onRowClick,
  loading = false,
  getSearchableText,
  searchPlaceholder = "Rechercher",
  resultLabel = "résultats",
  filtersSlot,
  activeFilterChips = [],
  onClearFilters,
  exportLabel,
  onExport,
  pageSize = DEFAULT_PAGE_SIZE,
  stickyFirstColumn = false,
  variant = "table",
  scrollToColumnKey,
  emptyState,
  className = "",
  scrollAreaClassName = "",
}: DataTableProps<T>) {
  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebouncedValue(searchInput, 300);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<{ key: string; direction: "asc" | "desc" } | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const autoScrolledForRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch]);

  const filteredRows = useMemo(() => {
    if (!getSearchableText || debouncedSearch.trim() === "") return rows;
    const needle = debouncedSearch.trim().toLowerCase();
    return rows.filter((row) => getSearchableText(row).toLowerCase().includes(needle));
  }, [rows, getSearchableText, debouncedSearch]);

  const sortedRows = useMemo(() => {
    if (!sort) return filteredRows;
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.sortAccessor) return filteredRows;
    const accessor = column.sortAccessor;
    const factor = sort.direction === "asc" ? 1 : -1;
    return [...filteredRows].sort((a, b) => {
      const va = accessor(a);
      const vb = accessor(b);
      if (va < vb) return -1 * factor;
      if (va > vb) return 1 * factor;
      return 0;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredRows, sort]);

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pageRows = sortedRows.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  function updateScrollShadows(): void {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 0);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }

  useEffect(() => {
    updateScrollShadows();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageRows, columns]);

  // Défilement initial vers `scrollToColumnKey` (une seule fois par valeur :
  // ne doit jamais reprendre la main sur un défilement fait par la personne).
  useEffect(() => {
    if (loading || !scrollToColumnKey) return;
    if (autoScrolledForRef.current === scrollToColumnKey) return;
    const el = scrollRef.current;
    if (!el) return;
    let offset = 0;
    for (const column of columns) {
      if (column.key === scrollToColumnKey) break;
      offset += column.widthPx ?? 0;
    }
    const stickyWidth = stickyFirstColumn ? (columns[0]?.widthPx ?? 0) : 0;
    el.scrollLeft = Math.max(0, offset - stickyWidth);
    autoScrolledForRef.current = scrollToColumnKey;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, scrollToColumnKey, stickyFirstColumn]);

  function toggleSort(key: string): void {
    setSort((current) => {
      if (!current || current.key !== key) return { key, direction: "asc" };
      if (current.direction === "asc") return { key, direction: "desc" };
      return null;
    });
  }

  const hasAnyFilter = debouncedSearch.trim() !== "" || activeFilterChips.length > 0;
  const rowHeightClass = variant === "grid" ? "h-11" : "min-h-[48px]";
  const cellPaddingClass = variant === "grid" ? "px-2 py-1" : "px-3 py-2";

  return (
    <div className={className}>
      {(getSearchableText || filtersSlot || onExport) && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {getSearchableText ? (
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
                type="search"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                className="h-control-sm w-full rounded-sm border border-border-strong bg-surface pl-8 pr-3 text-sm text-text placeholder:text-text-muted sm:w-64"
              />
            </div>
          ) : null}
          {filtersSlot}
          {onExport ? (
            <Button size="sm" variant="secondary" onClick={onExport}>
              {exportLabel ?? "Exporter (CSV)"}
            </Button>
          ) : null}
        </div>
      )}

      {activeFilterChips.length > 0 ? (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {activeFilterChips.map((chip) => (
            <span
              key={chip.label}
              className="inline-flex items-center gap-1 rounded-full bg-surface-muted px-2 py-1 text-xs text-text"
            >
              {chip.label}
              <button
                type="button"
                onClick={chip.onRemove}
                aria-label={`Retirer le filtre ${chip.label}`}
                className="text-text-muted hover:text-text"
              >
                ×
              </button>
            </span>
          ))}
          {onClearFilters ? (
            <button
              type="button"
              onClick={onClearFilters}
              className="text-xs font-medium text-primary-text hover:underline"
            >
              Effacer les filtres
            </button>
          ) : null}
        </div>
      ) : null}

      <p className="mb-2 text-xs text-text-muted">
        {sortedRows.length} {resultLabel}
      </p>

      <div className="relative">
        <div
          ref={scrollRef}
          onScroll={updateScrollShadows}
          className={["overflow-x-auto rounded-md border border-border", scrollAreaClassName].join(" ")}
        >
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 bg-surface-muted text-xs text-text-muted">
              <tr>
                {columns.map((column, index) => {
                  const isSticky = stickyFirstColumn && index === 0;
                  const sortable = Boolean(column.sortAccessor);
                  const isActiveSort = sort?.key === column.key;
                  const widthStyle = column.widthPx
                    ? { width: column.widthPx, minWidth: column.widthPx }
                    : undefined;
                  return (
                    <th
                      key={column.key}
                      scope="col"
                      aria-sort={
                        isActiveSort ? (sort?.direction === "asc" ? "ascending" : "descending") : "none"
                      }
                      style={isSticky ? { ...widthStyle, left: 0 } : widthStyle}
                      className={[
                        "whitespace-nowrap px-3 py-2 text-left font-medium",
                        column.align === "right" ? "text-right" : "",
                        isSticky ? "sticky z-[1] bg-surface-muted" : "",
                      ].join(" ")}
                    >
                      {sortable ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(column.key)}
                          className="inline-flex items-center gap-1"
                        >
                          {column.header}
                          <span aria-hidden="true">
                            {isActiveSort ? (sort?.direction === "asc" ? "▲" : "▼") : ""}
                          </span>
                        </button>
                      ) : (
                        column.header
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 5 }, (_, i) => (
                    <tr key={i}>
                      <td colSpan={columns.length} className="px-3 py-2">
                        <Skeleton variant="table-row" />
                      </td>
                    </tr>
                  ))
                : pageRows.map((row) => {
                    const id = getRowId(row);
                    return (
                      <tr
                        key={id}
                        tabIndex={onRowClick ? 0 : undefined}
                        onClick={onRowClick ? () => onRowClick(row) : undefined}
                        onKeyDown={
                          onRowClick
                            ? (e) => {
                                if (e.key === "Enter") onRowClick(row);
                              }
                            : undefined
                        }
                        className={[
                          rowHeightClass,
                          onRowClick ? "cursor-pointer hover:bg-surface-muted" : "",
                          "border-t border-border",
                        ].join(" ")}
                      >
                        {columns.map((column, index) => {
                          const isSticky = stickyFirstColumn && index === 0;
                          const widthStyle = column.widthPx
                            ? { width: column.widthPx, minWidth: column.widthPx }
                            : undefined;
                          return (
                            <td
                              key={column.key}
                              style={isSticky ? { ...widthStyle, left: 0 } : widthStyle}
                              className={[
                                cellPaddingClass,
                                column.align === "right" ? "text-right tabular-nums" : "",
                                isSticky ? "sticky z-[1] bg-surface" : "",
                              ].join(" ")}
                            >
                              {column.render(row)}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
            </tbody>
          </table>
        </div>
        {canScrollLeft ? (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 left-0 w-4"
            style={{ background: "linear-gradient(to right, var(--color-surface), transparent)" }}
          />
        ) : null}
        {canScrollRight ? (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 right-0 w-4"
            style={{ background: "linear-gradient(to left, var(--color-surface), transparent)" }}
          />
        ) : null}
      </div>

      {!loading && sortedRows.length === 0 ? (
        hasAnyFilter ? (
          <EmptyState
            variant="no-results"
            message={
              debouncedSearch.trim()
                ? `Aucun résultat pour « ${debouncedSearch.trim()} ».`
                : "Aucun résultat pour ces filtres."
            }
            actionLabel={onClearFilters ? "Effacer les filtres" : undefined}
            onAction={onClearFilters}
          />
        ) : (
          (emptyState ?? <EmptyState />)
        )
      ) : null}

      {!loading && sortedRows.length > 0 ? (
        <div className="mt-2 flex items-center justify-between text-xs text-text-muted">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
          >
            Précédent
          </Button>
          <span>
            {(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, sortedRows.length)} sur{" "}
            {sortedRows.length}
          </span>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages}
          >
            Suivant
          </Button>
        </div>
      ) : null}
    </div>
  );
}
