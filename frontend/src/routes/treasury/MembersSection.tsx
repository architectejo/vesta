import { useMemo, useState, type ReactNode } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  getContributionTypes,
  getMembers,
  type MemberOrdering,
  type MemberRow,
  type MemberStatusKey,
} from "../../api/treasury";
import {
  Avatar,
  Button,
  EmptyState,
  IconSearch,
  Skeleton,
  StatusBadge,
} from "../../design-system";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { formatAmount, formatDateFr } from "./money";

export const MEMBERS_QUERY_KEY = ["treasury", "members"] as const;
const CONTRIBUTION_TYPES_QUERY_KEY = ["treasury", "contribution-types"] as const;
const PAGE_SIZE = 20;

const STATUS_FILTERS: Array<{ key: MemberStatusKey; label: string }> = [
  { key: "in_good_standing", label: "En ordre" },
  { key: "in_debt", label: "En dette" },
  { key: "pending", label: "En attente" },
  { key: "suspended", label: "Suspendu" },
  { key: "left", label: "Parti" },
];

const ORDERING_OPTIONS: Array<{ value: MemberOrdering; label: string }> = [
  { value: "balance", label: "Solde croissant (dettes d'abord)" },
  { value: "-balance", label: "Solde décroissant" },
  { value: "name", label: "Nom (A à Z)" },
  { value: "-name", label: "Nom (Z à A)" },
  { value: "-last_payment", label: "Dernier paiement (récent d'abord)" },
  { value: "last_payment", label: "Dernier paiement (ancien d'abord)" },
];

const CONTROL_CLASS = "h-control-sm rounded-sm border border-border-strong bg-surface px-2 text-sm text-text";

interface Column {
  key: string;
  header: string;
  render: (row: MemberRow) => ReactNode;
  align?: "right";
  widthPx: number;
}

export interface MembersSectionProps {
  onOpen: (member: MemberRow) => void;
}

/**
 * « Membres du club » (CDC 4.4.6 ; fiche tresorerie-tableau-de-bord §3 point
 * 3). Recherche, filtres et tri sont exécutés par l'API ; l'interface affiche
 * les 20 premiers puis « Voir plus ». Statuts, soldes et raisons viennent de
 * l'API (aucun calcul ici).
 */
export function MembersSection({ onOpen }: MembersSectionProps) {
  const [search, setSearch] = useState("");
  const [statuses, setStatuses] = useState<MemberStatusKey[]>([]);
  const [typeId, setTypeId] = useState<number | "">("");
  const [ordering, setOrdering] = useState<MemberOrdering>("balance");
  const debouncedSearch = useDebouncedValue(search, 300);

  const typesQuery = useQuery({
    queryKey: CONTRIBUTION_TYPES_QUERY_KEY,
    queryFn: () => getContributionTypes(),
  });

  const query = useInfiniteQuery({
    queryKey: [...MEMBERS_QUERY_KEY, { q: debouncedSearch, statuses, typeId, ordering }],
    queryFn: ({ pageParam }) =>
      getMembers({
        q: debouncedSearch,
        status: statuses,
        contributionTypeIds: typeId === "" ? undefined : [typeId],
        ordering,
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
  });

  const rows = useMemo(() => query.data?.pages.flatMap((page) => page.results) ?? [], [query.data]);
  const total = query.data?.pages[0]?.count ?? 0;
  const hasFilter = debouncedSearch.trim() !== "" || statuses.length > 0 || typeId !== "";

  function toggleStatus(key: MemberStatusKey): void {
    setStatuses((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  }

  function clearFilters(): void {
    setSearch("");
    setStatuses([]);
    setTypeId("");
  }

  const columns: Column[] = [
    {
      key: "player",
      header: "Joueur",
      widthPx: 140,
      render: (row) => (
        <span className="flex items-center gap-2">
          <Avatar name={row.name} photoUrl={row.photo} size={24} />
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium text-text">{row.name}</span>
            {row.jersey_number != null ? (
              <span className="block text-xs text-text-muted">n° {row.jersey_number}</span>
            ) : null}
          </span>
        </span>
      ),
    },
    {
      key: "status",
      header: "Statut",
      widthPx: 130,
      render: (row) => (
        <span className="flex flex-wrap gap-1">
          {row.statuses.map((entry) => (
            <StatusBadge
              key={entry.key}
              status={entry.key}
              detail={entry.key === "in_debt" ? formatAmount(row.amount_due, row.currency) : undefined}
            />
          ))}
        </span>
      ),
    },
    {
      key: "monthly",
      header: "Type mensuel",
      widthPx: 120,
      render: (row) => <span className="text-sm text-text">{row.monthly_type?.name ?? "—"}</span>,
    },
    {
      key: "balance",
      header: "Solde",
      align: "right",
      widthPx: 100,
      render: (row) => (
        <span className={Number(row.balance) < 0 ? "text-status-danger-fg" : "text-text"}>
          {formatAmount(row.balance, row.currency)}
        </span>
      ),
    },
    {
      key: "last_payment",
      header: "Dernier paiement",
      widthPx: 120,
      render: (row) => (
        <span className="text-sm text-text">{row.last_payment_on ? formatDateFr(row.last_payment_on) : "—"}</span>
      ),
    },
  ];

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4" aria-label="Membres du club">
      <h2 className="mb-3 text-base font-semibold text-text">Membres du club</h2>

      <div className="mb-3 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1 basis-48">
            <IconSearch
              aria-hidden="true"
              className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
            />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Rechercher un joueur"
              aria-label="Rechercher un joueur"
              className={`${CONTROL_CLASS} w-full pl-8`}
            />
          </div>
          <select
            aria-label="Type de cotisation"
            value={typeId}
            onChange={(event) => setTypeId(event.target.value === "" ? "" : Number(event.target.value))}
            className={`${CONTROL_CLASS} min-w-0 max-w-full`}
          >
            <option value="">Tous les types</option>
            {(typesQuery.data ?? []).map((type) => (
              <option key={type.id} value={type.id}>
                {type.name}
              </option>
            ))}
          </select>
          <select
            aria-label="Trier par"
            value={ordering}
            onChange={(event) => setOrdering(event.target.value as MemberOrdering)}
            className={`${CONTROL_CLASS} min-w-0 max-w-full`}
          >
            {ORDERING_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div role="group" aria-label="Statut" className="flex flex-wrap items-center gap-2">
          {STATUS_FILTERS.map((filter) => {
            const active = statuses.includes(filter.key);
            return (
              <button
                key={filter.key}
                type="button"
                aria-pressed={active}
                onClick={() => toggleStatus(filter.key)}
                className={[
                  "h-control-sm rounded-full border px-3 text-sm",
                  active
                    ? "border-primary bg-surface-muted font-medium text-text"
                    : "border-border-strong bg-surface text-text-muted",
                ].join(" ")}
              >
                {filter.label}
              </button>
            );
          })}
          {hasFilter ? (
            <button type="button" onClick={clearFilters} className="text-xs font-medium text-primary-text hover:underline">
              Effacer les filtres
            </button>
          ) : null}
        </div>
      </div>

      {query.isError ? (
        <EmptyState
          variant="error"
          message="Impossible de charger les membres du club."
          actionLabel="Réessayer"
          onAction={() => void query.refetch()}
        />
      ) : (
        <>
          {query.isLoading ? (
            <div role="status" aria-label="Chargement des membres" className="space-y-2">
              {[0, 1, 2, 3, 4].map((index) => (
                <Skeleton key={index} variant="table-row" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              variant={hasFilter ? "no-results" : "default"}
              message={hasFilter ? "Aucun joueur ne correspond à ces filtres." : "Aucun joueur dans le club."}
            />
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full border-collapse text-sm">
                <thead className="bg-surface-muted text-xs text-text-muted">
                  <tr>
                    {columns.map((column, index) => (
                      <th
                        key={column.key}
                        scope="col"
                        style={{ width: column.widthPx, minWidth: column.widthPx, ...(index === 0 ? { left: 0 } : {}) }}
                        className={[
                          "whitespace-nowrap px-3 py-2 font-medium",
                          column.align === "right" ? "text-right" : "text-left",
                          index === 0 ? "sticky z-[1] bg-surface-muted" : "",
                        ].join(" ")}
                      >
                        {column.header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.membership_id}
                      tabIndex={0}
                      onClick={() => onOpen(row)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") onOpen(row);
                      }}
                      aria-label={`Situation financière de ${row.name}`}
                      className="min-h-[48px] cursor-pointer border-t border-border hover:bg-surface-muted"
                    >
                      {columns.map((column, index) => (
                        <td
                          key={column.key}
                          style={{ width: column.widthPx, minWidth: column.widthPx, ...(index === 0 ? { left: 0 } : {}) }}
                          className={[
                            "px-3 py-2",
                            column.align === "right" ? "text-right tabular-nums" : "",
                            index === 0 ? "sticky z-[1] bg-surface" : "",
                          ].join(" ")}
                        >
                          {column.render(row)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {rows.length > 0 ? (
            <p className="mt-2 text-xs text-text-muted">
              {rows.length} sur {total} joueurs
            </p>
          ) : null}
          {query.hasNextPage ? (
            <div className="mt-2 flex flex-col items-center gap-1">
              <Button
                size="sm"
                variant="secondary"
                loading={query.isFetchingNextPage}
                loadingLabel="Chargement…"
                onClick={() => void query.fetchNextPage()}
              >
                Voir plus
              </Button>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
