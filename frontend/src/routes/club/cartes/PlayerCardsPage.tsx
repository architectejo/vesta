import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError } from "../../../api/client";
import type { ClubPlayerPosition } from "../../../api/clubs";
import {
  listPlayerCards,
  type PlayerCardAvailabilityFilter,
  type PlayerCardListRow,
  type PlayerCardOrdering,
  type PlayerCardStatusFilter,
} from "../../../api/playerCards";
import {
  Avatar,
  Button,
  DataTable,
  EmptyState,
  Modal,
  PlayerTradingCard,
  SegmentedControl,
  Skeleton,
  StatusBadge,
  useClubBranding,
  type DataTableColumn,
  type PlayerSearchResult,
} from "../../../design-system";
import { useDebouncedValue } from "../../../hooks/useDebouncedValue";
import { useMediaQuery } from "../../../hooks/useMediaQuery";
import { CardsComparisonModal } from "./CardsComparisonModal";
import { PlayerDetail, PlayerDetailModal } from "./PlayerDetail";
import { availabilityBadge, formatPercent, formatRating, plural } from "./playerCardFormat";

const PAGE_SIZE = 24;
const MAX_COMPARE = 4;

const POSITIONS: Array<{ value: ClubPlayerPosition | ""; label: string }> = [
  { value: "", label: "Tous" },
  { value: "goalkeeper", label: "Gardien" },
  { value: "defender", label: "Défenseur" },
  { value: "midfielder", label: "Milieu" },
  { value: "forward", label: "Attaquant" },
];

const SORTS: Array<{ value: PlayerCardOrdering; label: string }> = [
  { value: "name", label: "Nom" },
  { value: "number", label: "Numéro" },
  { value: "-average_rating", label: "Note moyenne" },
  { value: "-goals", label: "Buts" },
  { value: "-assists", label: "Passes décisives" },
  { value: "-attendance_rate", label: "Taux de présence" },
  { value: "-matches_played", label: "Matchs joués" },
];

function toSearchResult(row: PlayerCardListRow): PlayerSearchResult {
  return {
    id: row.membership_id,
    firstName: row.first_name,
    lastName: row.last_name,
    number: row.jersey_number,
    position: row.position_label,
    photoUrl: row.photo,
  };
}

/** Bande de statistiques sous une carte (mobile) : tous les libellés en toutes lettres. */
function StatsStrip({ row }: { row: PlayerCardListRow }) {
  const s = row.stats;
  return (
    <div className="mt-1 space-y-0.5 text-center text-[13px] tabular-nums text-text">
      <p>
        {plural(s.matches_played, "match", "matchs")} · {plural(s.goals, "but", "buts")} ·{" "}
        {plural(s.assists, "passe", "passes")}
      </p>
      <p>
        {plural(s.yellow_cards + s.red_cards, "carton", "cartons")} · présence {formatPercent(s.attendance_rate)} · note{" "}
        {formatRating(s.average_rating)}
      </p>
      {row.recent_ratings.length > 0 ? (
        <p className="text-text-muted">Dernières notes : {row.recent_ratings.map(formatRating).join(" · ")}</p>
      ) : null}
    </div>
  );
}

export function PlayerCardsPage() {
  const branding = useClubBranding();
  const isDesktop = useMediaQuery("(min-width: 1024px)");
  const [searchParams, setSearchParams] = useSearchParams();

  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput, 300);
  const [position, setPosition] = useState<ClubPlayerPosition | "">("");
  const [status, setStatus] = useState<PlayerCardStatusFilter>("active");
  const [availability, setAvailability] = useState<PlayerCardAvailabilityFilter | "">("");
  const [seasonId, setSeasonId] = useState<number | null>(null);
  const [ordering, setOrdering] = useState<PlayerCardOrdering>("name");
  const [view, setView] = useState<"cards" | "table">("cards");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);

  const [compareMode, setCompareMode] = useState(false);
  const [picked, setPicked] = useState<PlayerSearchResult[]>([]);
  const [comparison, setComparison] = useState<PlayerSearchResult[] | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);

  const query = useInfiniteQuery({
    queryKey: ["player-cards", { search, position, status, availability, seasonId, ordering }],
    queryFn: ({ pageParam }) =>
      listPlayerCards({
        search: search.trim() || undefined,
        position: position || undefined,
        status,
        availability: availability || undefined,
        season: seasonId ?? undefined,
        ordering,
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.has_more ? last.offset + last.limit : undefined),
    retry: false,
  });

  const first = query.data?.pages[0];
  const lastPage = query.data?.pages[query.data.pages.length - 1];
  const rows = useMemo(() => {
    const seen = new Set<number>();
    const out: PlayerCardListRow[] = [];
    for (const page of query.data?.pages ?? []) {
      for (const row of page.results) {
        if (!seen.has(row.membership_id)) {
          seen.add(row.membership_id);
          out.push(row);
        }
      }
    }
    return out;
  }, [query.data]);

  const canSeeAvailability = first?.can_see_availability ?? false;
  const canCompare = first?.can_compare ?? false;
  const seasonLabel = lastPage?.season_label ?? first?.season_label ?? null;
  const activeSeasonId = first?.season_id ?? null;
  const total = lastPage?.count ?? 0;

  // Joueur choisi (ordinateur) : `?joueur=`, sinon le premier de la liste.
  const joueurParam = Number(searchParams.get("joueur"));
  const selectedRow = rows.find((r) => r.membership_id === joueurParam) ?? rows[0] ?? null;
  function select(row: PlayerCardListRow): void {
    setSearchParams({ joueur: String(row.membership_id) }, { replace: true });
  }

  const filterCount =
    (position ? 1 : 0) + (status !== "active" ? 1 : 0) + (availability ? 1 : 0) + (seasonId !== null ? 1 : 0);

  function resetFilters(): void {
    setSearchInput("");
    setPosition("");
    setStatus("active");
    setAvailability("");
    setSeasonId(null);
  }

  function togglePick(row: PlayerCardListRow): void {
    setPicked((current) => {
      if (current.some((p) => p.id === row.membership_id)) return current.filter((p) => p.id !== row.membership_id);
      if (current.length >= MAX_COMPARE) return current;
      return [...current, toSearchResult(row)];
    });
  }

  function openRow(row: PlayerCardListRow, forceModal = false): void {
    if (compareMode) {
      togglePick(row);
    } else if (isDesktop && view === "cards" && !forceModal) {
      select(row);
    } else {
      setDetailId(row.membership_id);
    }
  }

  // Flèches du clavier dans la grille (ordinateur).
  useEffect(() => {
    if (!isDesktop || view !== "cards") return undefined;
    function onKey(event: KeyboardEvent): void {
      const target = event.target as HTMLElement | null;
      if (!target?.closest("[data-cards-grid]")) return;
      const step = { ArrowLeft: -1, ArrowUp: -2, ArrowRight: 1, ArrowDown: 2 }[event.key];
      if (step === undefined || !selectedRow) return;
      const index = rows.findIndex((r) => r.membership_id === selectedRow.membership_id);
      const next = rows[index + step];
      if (next) {
        event.preventDefault();
        select(next);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDesktop, view, rows, selectedRow]);

  const errorDetail =
    query.error instanceof ApiError && query.error.status === 400 ? query.error.detail : null;
  const detailIndex = detailId === null ? -1 : rows.findIndex((r) => r.membership_id === detailId);
  const sortLabel = SORTS.find((s) => s.value === ordering)?.label ?? "Nom";
  const seasons = first?.seasons ?? [];
  const seasonIndex = seasons.findIndex((s) => s.id === (seasonId ?? activeSeasonId));

  const columns: Array<DataTableColumn<PlayerCardListRow>> = [
    {
      key: "player",
      header: "Joueur",
      widthPx: 160,
      render: (row) => (
        <span className="flex items-center gap-2">
          {compareMode ? (
            <input
              type="checkbox"
              aria-label={`Comparer ${row.first_name} ${row.last_name}`}
              checked={picked.some((p) => p.id === row.membership_id)}
              disabled={picked.length >= MAX_COMPARE && !picked.some((p) => p.id === row.membership_id)}
              onClick={(e) => e.stopPropagation()}
              onChange={() => togglePick(row)}
              className="h-5 w-5"
            />
          ) : null}
          <Avatar name={`${row.first_name} ${row.last_name}`} photoUrl={row.photo} size={32} />
          <span className="text-sm text-text">
            {row.first_name} {row.last_name}
          </span>
        </span>
      ),
    },
    { key: "number", header: "Numéro", align: "right", sortAccessor: (r) => r.jersey_number ?? 9999, render: (r) => r.jersey_number ?? "—" },
    { key: "position", header: "Poste", render: (r) => r.position_label || "—" },
    { key: "matches", header: "Matchs", align: "right", sortAccessor: (r) => r.stats.matches_played, render: (r) => r.stats.matches_played },
    { key: "goals", header: "Buts", align: "right", sortAccessor: (r) => r.stats.goals, render: (r) => r.stats.goals },
    { key: "assists", header: "Passes décisives", align: "right", sortAccessor: (r) => r.stats.assists, render: (r) => r.stats.assists },
    {
      key: "cards",
      header: "Cartons",
      render: (r) => `${plural(r.stats.yellow_cards, "jaune", "jaunes")}, ${plural(r.stats.red_cards, "rouge", "rouges")}`,
    },
    {
      key: "attendance",
      header: "Taux de présence",
      align: "right",
      sortAccessor: (r) => r.stats.attendance_rate ?? -1,
      render: (r) => formatPercent(r.stats.attendance_rate),
    },
    {
      key: "rating",
      header: "Note moyenne",
      align: "right",
      sortAccessor: (r) => Number(r.stats.average_rating ?? -1),
      render: (r) => formatRating(r.stats.average_rating),
    },
    {
      key: "form",
      header: "Forme",
      render: (r) => (r.recent_ratings.length ? r.recent_ratings.map(formatRating).join(" · ") : "—"),
    },
  ];

  const toolbar = (
    <div className="sticky top-0 z-10 space-y-2 bg-surface-page py-2">
      <input
        type="search"
        value={searchInput}
        onChange={(e) => setSearchInput(e.target.value)}
        placeholder="Nom ou numéro"
        aria-label="Nom ou numéro"
        className="h-control-sm w-full rounded-sm border border-border-strong bg-surface px-3 text-sm text-text placeholder:text-text-muted"
      />
      <div role="group" aria-label="Poste" className="flex gap-2 overflow-x-auto pb-1">
        {POSITIONS.map((p) => (
          <button
            key={p.value || "all"}
            type="button"
            aria-pressed={position === p.value}
            onClick={() => setPosition(p.value)}
            className={[
              "h-control-sm shrink-0 rounded-full border px-3 text-sm",
              position === p.value
                ? "border-primary bg-primary text-on-primary"
                : "border-border-strong bg-surface text-text",
            ].join(" ")}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" onClick={() => setFiltersOpen(true)}>
          {filterCount > 0 ? `Filtres (${filterCount})` : "Filtres"}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => setSortOpen(true)}>
          {`Trier : ${sortLabel}`}
        </Button>
        <SegmentedControl
          label="Affichage"
          hideLabel
          value={view}
          onChange={setView}
          options={[
            { value: "cards", label: "Cartes" },
            { value: "table", label: "Tableau" },
          ]}
        />
      </div>
    </div>
  );

  let body;
  if (query.isLoading) {
    body = (
      <div aria-busy="true" aria-label="Chargement des cartes" className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} variant="player-card" />
        ))}
      </div>
    );
  } else if (query.isError) {
    body = (
      <EmptyState
        variant="error"
        message={errorDetail ?? "Impossible de charger les cartes des joueurs."}
        actionLabel={errorDetail ? "Réinitialiser les filtres" : "Réessayer"}
        onAction={errorDetail ? resetFilters : () => void query.refetch()}
      />
    );
  } else if (rows.length === 0) {
    const filtered = Boolean(search.trim()) || filterCount > 0;
    body = filtered ? (
      <EmptyState
        variant="no-results"
        message="Aucun joueur ne correspond à ces filtres."
        actionLabel="Réinitialiser les filtres"
        onAction={resetFilters}
      />
    ) : (
      <EmptyState message="Aucun joueur dans le club pour l'instant." />
    );
  } else if (view === "table") {
    body = (
      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.membership_id}
        onRowClick={(r) => openRow(r, true)}
        stickyFirstColumn
        pageSize={Math.max(25, rows.length)}
        resultLabel="joueurs"
      />
    );
  } else {
    const grid = (
      <ul
        data-cards-grid
        className={["grid gap-3", isDesktop ? "grid-cols-2 min-[1440px]:grid-cols-3" : "grid-cols-2 min-[600px]:grid-cols-3"].join(" ")}
      >
        {rows.map((row) => {
          const isPicked = picked.some((p) => p.id === row.membership_id);
          const isCurrent = isDesktop && !compareMode && selectedRow?.membership_id === row.membership_id;
          const badge = row.availability ? availabilityBadge(row.availability) : null;
          return (
            <li
              key={row.membership_id}
              aria-current={isCurrent ? "true" : undefined}
              className={["relative min-w-0 rounded-md p-1", isCurrent ? "ring-2 ring-primary" : ""].join(" ")}
            >
              {compareMode ? (
                <label className="absolute left-0 top-0 z-10 flex h-11 w-11 items-center justify-center">
                  <input
                    type="checkbox"
                    aria-label={`Comparer ${row.first_name} ${row.last_name}`}
                    checked={isPicked}
                    disabled={!isPicked && picked.length >= MAX_COMPARE}
                    onChange={() => togglePick(row)}
                    className="h-5 w-5"
                  />
                </label>
              ) : null}
              <PlayerTradingCard
                size="sm"
                motion="static"
                firstName={row.first_name}
                lastName={row.last_name}
                photoUrl={row.photo}
                positionLabel={row.position_label}
                jerseyNumber={row.jersey_number}
                clubLogoUrl={branding?.logoUrl ?? null}
                clubName={branding?.name ?? ""}
                overallRating={row.overall_rating}
                onOpen={() => openRow(row)}
              />
              {badge ? (
                <p className="mt-1 text-center">
                  <StatusBadge status={badge.status} detail={badge.detail} />
                </p>
              ) : null}
              {!isDesktop ? <StatsStrip row={row} /> : null}
            </li>
          );
        })}
      </ul>
    );
    body = isDesktop ? (
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-5 max-h-[calc(100vh-14rem)] overflow-y-auto pr-1">{grid}</div>
        <div className="col-span-7">
          <div className="sticky top-24">
            {selectedRow ? (
              <PlayerDetail
                key={selectedRow.membership_id}
                row={selectedRow}
                seasonId={activeSeasonId}
                seasonLabel={seasonLabel}
                layout="side"
              />
            ) : null}
            {selectedRow && canCompare ? (
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => setComparison([toSearchResult(selectedRow)])}>
                  Comparer avec…
                </Button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    ) : (
      grid
    );
  }

  return (
    <div className="space-y-3 pb-16">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-text">Cartes des joueurs</h1>
          {first ? (
            <p className="text-sm text-text-muted">
              {[branding?.name, seasonLabel ? `Saison ${seasonLabel}` : null, plural(total, "joueur", "joueurs")]
                .filter(Boolean)
                .join(" · ")}
            </p>
          ) : null}
        </div>
        {canCompare ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setCompareMode((v) => !v);
              setPicked([]);
            }}
          >
            {compareMode ? "Quitter la comparaison" : "Comparer"}
          </Button>
        ) : null}
      </header>

      {toolbar}

      {body}

      {query.hasNextPage || (rows.length > 0 && !query.isLoading) ? (
        <div className="space-y-2 text-center">
          <p className="text-sm text-text-muted">
            {rows.length} sur {plural(total, "joueur", "joueurs")}
          </p>
          {query.hasNextPage ? (
            <Button
              size="md"
              variant="secondary"
              loading={query.isFetchingNextPage}
              loadingLabel="Chargement…"
              onClick={() => void query.fetchNextPage()}
            >
              Voir plus
            </Button>
          ) : null}
        </div>
      ) : null}

      {compareMode ? (
        <div className="fixed inset-x-0 bottom-0 z-20 flex flex-wrap items-center justify-between gap-2 border-t border-border bg-surface p-3">
          <div className="text-sm text-text">
            <p>
              {plural(picked.length, "joueur choisi", "joueurs choisis")} · 2 à 4
            </p>
            {picked.length >= MAX_COMPARE ? (
              <p className="text-xs text-text-muted">4 joueurs au maximum. Retirez-en un pour en ajouter un autre.</p>
            ) : null}
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="primary"
              disabled={picked.length < 2}
              onClick={() => setComparison(picked)}
            >
              {`Comparer (${picked.length})`}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setCompareMode(false);
                setPicked([]);
              }}
            >
              Annuler
            </Button>
          </div>
        </div>
      ) : null}

      {filtersOpen ? (
        <Modal
          open
          onClose={() => setFiltersOpen(false)}
          title="Filtres"
          size="sm"
          cancelLabel="Fermer"
          footer={
            <div className="flex w-full items-center justify-between gap-2">
              <Button variant="secondary" size="md" onClick={resetFilters}>
                Réinitialiser
              </Button>
              <Button variant="primary" size="md" onClick={() => setFiltersOpen(false)}>
                {`Afficher ${plural(total, "joueur", "joueurs")}`}
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            <SegmentedControl
              label="Statut"
              value={status}
              onChange={setStatus}
              options={[
                { value: "active", label: "Joueurs actifs" },
                { value: "left", label: "Anciens joueurs" },
              ]}
            />
            {canSeeAvailability ? (
              <SegmentedControl
                label="Disponibilité"
                value={availability === "" ? "all" : availability}
                onChange={(v) => setAvailability(v === "all" ? "" : v)}
                options={[
                  { value: "all", label: "Tous" },
                  { value: "available", label: "Disponibles" },
                  { value: "unavailable", label: "Indisponibles" },
                ]}
              />
            ) : null}
            {seasons.length > 0 ? (
              <div>
                <p className="mb-1 text-sm font-medium text-text">Saison</p>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    aria-label="Saison précédente"
                    disabled={seasonIndex < 0 || seasonIndex >= seasons.length - 1}
                    onClick={() => setSeasonId(seasons[seasonIndex + 1]?.id ?? null)}
                  >
                    ‹
                  </Button>
                  <span className="text-sm text-text">{seasons[seasonIndex]?.label ?? seasonLabel}</span>
                  <Button
                    size="sm"
                    variant="secondary"
                    aria-label="Saison suivante"
                    disabled={seasonIndex <= 0}
                    onClick={() => setSeasonId(seasons[seasonIndex - 1]?.id ?? null)}
                  >
                    ›
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        </Modal>
      ) : null}

      {sortOpen ? (
        <Modal open onClose={() => setSortOpen(false)} title="Trier les joueurs" size="sm" hideFooter cancelLabel="Fermer">
          <ul className="space-y-1">
            {SORTS.map((s) => (
              <li key={s.value}>
                <button
                  type="button"
                  aria-pressed={ordering === s.value}
                  onClick={() => {
                    setOrdering(s.value);
                    setSortOpen(false);
                  }}
                  className={[
                    "h-control-md w-full rounded-sm border px-3 text-left text-sm",
                    ordering === s.value
                      ? "border-primary bg-primary text-on-primary"
                      : "border-border-strong bg-surface text-text",
                  ].join(" ")}
                >
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
        </Modal>
      ) : null}

      {detailIndex >= 0 ? (
        <PlayerDetailModal
          rows={rows}
          index={detailIndex}
          seasonId={activeSeasonId}
          seasonLabel={seasonLabel}
          canCompare={canCompare}
          onNavigate={(i) => setDetailId(rows[i]?.membership_id ?? null)}
          onCompare={(row) => setComparison([toSearchResult(row)])}
          onClose={() => setDetailId(null)}
        />
      ) : null}

      {comparison ? <CardsComparisonModal initialPlayers={comparison} onClose={() => setComparison(null)} /> : null}
    </div>
  );
}
