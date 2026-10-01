import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ApiError, triggerBlobDownload } from "../../api/client";
import { getMyProfile } from "../../api/clubs";
import {
  downloadContributionGridCsv,
  getFullContributionGrid,
  getGridContributionTypes,
  getTreasuryCapabilities,
  type GridContributionType,
  type GridMonth,
  type GridRow,
} from "../../api/treasury";
import { Avatar, Button, DataTable, EmptyState, Loader, SegmentedControl, useToast, type DataTableColumn } from "../../design-system";
import { useAuth } from "../../auth/AuthContext";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { FinancialSituationModal, type FinancialSituationTarget } from "./FinancialSituationModal";
import { GridStateDot, cellVisual } from "./gridCellVisuals";
import { ImportContributionsModal } from "./ImportContributionsModal";
import { formatNumber } from "./money";
import { MonthDetailModal, type MonthDetailTarget } from "./MonthDetailModal";
import { getTreasuryAccess } from "./treasuryAccess";

const TYPES_QUERY_KEY = ["treasury", "grid-types"] as const;
const CAPABILITIES_QUERY_KEY = ["treasury", "capabilities"] as const;
const GRID_QUERY_KEY_PREFIX = ["treasury", "grid"] as const;

// Purement présentationnel (noms de mois du calendrier), affiché le temps que
// l'API renvoie `months` avec les périodes réelles de l'année choisie :
// aucun calcul métier, seulement les intitulés d'en-tête de colonne.
const FALLBACK_MONTH_LABELS = [
  "janv.", "févr.", "mars", "avr.", "mai", "juin",
  "juil.", "août", "sept.", "oct.", "nov.", "déc.",
];

function apiErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.detail : fallback;
}

interface GridCellButtonProps {
  cell: GridRow["cells"][number];
  monthLabel: string;
  onClick: () => void;
}

function GridCellButton({ cell, monthLabel, onClick }: GridCellButtonProps) {
  const visual = cellVisual(cell);
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`${monthLabel} : ${cell.state_label}, ${visual.text}`}
      className={["flex h-9 w-full items-center justify-center gap-1 rounded-sm text-xs tabular-nums", visual.bgClass, visual.textClass].join(" ")}
    >
      {visual.dot}
      <span>{visual.text}</span>
    </button>
  );
}

function LegendItem({ dot, swatchClass, label }: { dot?: ReactNode; swatchClass?: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {dot ?? <span aria-hidden="true" className={["h-2.5 w-2.5 rounded-sm", swatchClass ?? ""].join(" ")} />}
      {label}
    </span>
  );
}

function GridLegend({ currency }: { currency: string }) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted">
      <LegendItem dot={<GridStateDot shape="full" color="success" />} label="Payé" />
      <LegendItem dot={<GridStateDot shape="half" color="warning" />} label="Partiel" />
      <LegendItem dot={<GridStateDot shape="empty" color="danger" />} label="Impayé échu" />
      <LegendItem swatchClass="bg-cell-upcoming-bg" label="À venir" />
      {currency ? <span>Montants en {currency}.</span> : null}
    </div>
  );
}

interface TypeChipsProps {
  active: GridContributionType[];
  archived: GridContributionType[];
  selectedTypeId: number | null;
  onSelect: (id: number) => void;
}

function TypeChips({ active, archived, selectedTypeId, onSelect }: TypeChipsProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const selectedIsArchived = archived.some((type) => type.id === selectedTypeId);

  useEffect(() => {
    if (!menuOpen) return undefined;
    function handleClick(event: MouseEvent): void {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenuOpen(false);
    }
    function handleKey(event: KeyboardEvent): void {
      if (event.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [menuOpen]);

  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-1" role="group" aria-label="Type de cotisation">
      {active.map((type) => {
        const isSelected = type.id === selectedTypeId;
        return (
          <button
            key={type.id}
            type="button"
            aria-pressed={isSelected}
            onClick={() => onSelect(type.id)}
            className={[
              "h-9 shrink-0 whitespace-nowrap rounded-full border px-3 text-sm font-medium",
              isSelected
                ? "border-primary bg-primary text-on-primary"
                : "border-border-strong bg-surface text-text hover:bg-surface-muted",
            ].join(" ")}
          >
            {type.name}
          </button>
        );
      })}
      {archived.length > 0 ? (
        <div className="relative shrink-0" ref={menuRef}>
          <button
            type="button"
            aria-haspopup="true"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
            className={[
              "h-9 shrink-0 whitespace-nowrap rounded-full border px-3 text-sm font-medium",
              selectedIsArchived
                ? "border-primary bg-primary text-on-primary"
                : "border-border-strong bg-surface text-text hover:bg-surface-muted",
            ].join(" ")}
          >
            Types archivés
          </button>
          {menuOpen ? (
            <div className="absolute left-0 top-full z-10 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated">
              {archived.map((type) => (
                <button
                  key={type.id}
                  type="button"
                  onClick={() => {
                    onSelect(type.id);
                    setMenuOpen(false);
                  }}
                  className="flex w-full items-center px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                >
                  {type.name}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Écran « Grille des cotisations » (fiche `docs/ecrans/tresorerie-grille-cotisations.md`,
 * CDC 4.4.7). Accès : Président, Vice-président, Trésorier, Trésorier
 * adjoint (matrice 2.4 ; le 4.4.7 ne cite pas le VP, point ouvert de la
 * fiche §7, défaut appliqué = la matrice fait foi). Aucun état de cellule
 * n'est calculé ici : tout vient de `ContributionGridView`.
 */
export function GrilleCotisationsPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  const [selectedTypeId, setSelectedTypeId] = useState<number | null>(null);
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebouncedValue(searchInput, 300);
  const [filterMode, setFilterMode] = useState<"all" | "unpaid">("all");
  const [helpDismissed, setHelpDismissed] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [monthDetailTarget, setMonthDetailTarget] = useState<MonthDetailTarget | null>(null);
  const [situationTarget, setSituationTarget] = useState<FinancialSituationTarget | null>(null);
  const [importOpen, setImportOpen] = useState(false);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const { canRead, canWrite } = getTreasuryAccess(profileQuery.data?.roles);

  const typesQuery = useQuery({
    queryKey: TYPES_QUERY_KEY,
    queryFn: () => getGridContributionTypes(),
    enabled: canRead,
  });
  const capabilitiesQuery = useQuery({
    queryKey: CAPABILITIES_QUERY_KEY,
    queryFn: () => getTreasuryCapabilities(),
    enabled: canRead,
  });
  const canRecordPayments = capabilitiesQuery.data?.capabilities.can_record_payments ?? false;

  // Sélectionne le type par défaut (premier type mensuel obligatoire, fourni
  // par l'API) une seule fois, dès que la liste est connue.
  useEffect(() => {
    if (selectedTypeId !== null || !typesQuery.data) return;
    const defaultId = typesQuery.data.default_type_id ?? typesQuery.data.active[0]?.id ?? null;
    if (defaultId !== null) setSelectedTypeId(defaultId);
  }, [typesQuery.data, selectedTypeId]);

  const gridQuery = useQuery({
    queryKey: [...GRID_QUERY_KEY_PREFIX, selectedTypeId, year],
    queryFn: () => getFullContributionGrid(selectedTypeId as number, year),
    enabled: canRead && selectedTypeId !== null,
  });

  const currency = typesQuery.data?.currency ?? "";
  const allRows = gridQuery.data?.results ?? [];
  const months: GridMonth[] =
    gridQuery.data?.months ??
    FALLBACK_MONTH_LABELS.map((label, index) => ({ period: "", month: index + 1, label, long_label: label }));

  const filteredRows = useMemo(() => {
    let rows = allRows;
    if (filterMode === "unpaid") rows = rows.filter((row) => row.has_unpaid);
    const needle = debouncedSearch.trim().toLowerCase();
    if (needle) {
      rows = rows.filter((row) => {
        const name = `${row.first_name} ${row.last_name}`.toLowerCase();
        const number = row.jersey_number != null ? String(row.jersey_number) : "";
        return name.includes(needle) || number.includes(needle);
      });
    }
    return rows;
  }, [allRows, filterMode, debouncedSearch]);

  const playerColumnWidth = isDesktop ? 200 : 120;

  function openMonthDetail(row: GridRow, month: number): void {
    if (selectedTypeId === null) return;
    setMonthDetailTarget({ typeId: selectedTypeId, year, membershipId: row.membership_id, month });
  }

  function openSituation(row: GridRow): void {
    if (!gridQuery.data || selectedTypeId === null) return;
    setSituationTarget({
      row,
      months: gridQuery.data.months,
      contributionTypeId: selectedTypeId,
      contributionTypeName: gridQuery.data.contribution_type.name,
      year,
    });
  }

  const columns = useMemo<Array<DataTableColumn<GridRow>>>(() => {
    const monthColumns: Array<DataTableColumn<GridRow>> = months.map((month, index) => ({
      key: `month-${month.month}`,
      header: month.label,
      widthPx: 56,
      render: (row: GridRow) => {
        const cell = row.cells[index];
        if (!cell) return null;
        return (
          <GridCellButton cell={cell} monthLabel={month.long_label || month.label} onClick={() => openMonthDetail(row, month.month)} />
        );
      },
    }));
    return [
      {
        key: "player",
        header: "Joueur",
        widthPx: playerColumnWidth,
        render: (row: GridRow) => (
          <button
            type="button"
            onClick={() => openSituation(row)}
            className="flex w-full items-center gap-2 text-left"
          >
            <Avatar name={`${row.first_name} ${row.last_name}`} photoUrl={row.photo} size={24} />
            <span className="min-w-0">
              <span className="block break-words text-sm text-text" style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                {row.first_name} {row.last_name}
              </span>
              {row.jersey_number != null ? <span className="block text-xs text-text-muted">n° {row.jersey_number}</span> : null}
            </span>
          </button>
        ),
      },
      ...monthColumns,
      {
        key: "total",
        header: "Total",
        widthPx: 72,
        align: "right",
        sortAccessor: (row: GridRow) => Number(row.total),
        render: (row: GridRow) => <span className="tabular-nums text-text">{formatNumber(row.total)}</span>,
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [months, playerColumnWidth, selectedTypeId, year]);

  const scrollToColumnKey = useMemo(() => {
    const today = gridQuery.data?.today;
    if (!today) return undefined;
    const todayDate = new Date(`${today}T00:00:00`);
    if (Number.isNaN(todayDate.getTime()) || todayDate.getFullYear() !== year) return undefined;
    return `month-${todayDate.getMonth() + 1}`;
  }, [gridQuery.data?.today, year]);

  function buildEmptyState(): ReactNode {
    if (allRows.length === 0) {
      return <EmptyState message="Aucun joueur n'est rattaché à ce type de cotisation." />;
    }
    const trimmed = debouncedSearch.trim();
    if (trimmed !== "") {
      return (
        <EmptyState
          variant="no-results"
          message={`Aucun joueur ne correspond à « ${trimmed} ».`}
          actionLabel="Effacer la recherche"
          onAction={() => setSearchInput("")}
        />
      );
    }
    if (filterMode === "unpaid") {
      return <EmptyState message={`Aucun impayé pour ce type en ${year}.`} />;
    }
    return <EmptyState />;
  }

  async function handleExport(): Promise<void> {
    if (selectedTypeId === null) return;
    setExporting(true);
    try {
      const { blob, filename } = await downloadContributionGridCsv(selectedTypeId, year);
      triggerBlobDownload(blob, filename);
      showToast("Export téléchargé.");
    } catch (error) {
      showToast(apiErrorMessage(error, "Export impossible. Réessayez."));
    } finally {
      setExporting(false);
    }
  }

  function handleMonthPaymentRecorded(): void {
    void queryClient.invalidateQueries({ queryKey: GRID_QUERY_KEY_PREFIX });
    void queryClient.invalidateQueries({ queryKey: ["treasury", "grid-month-detail"] });
  }

  // Version réduite de la modale « Situation financière » (voir
  // FinancialSituationModal) : pas de requête propre à rafraîchir après un
  // paiement, on referme donc la modale plutôt que d'afficher des chiffres
  // périmés.
  function handleSituationPaymentRecorded(): void {
    void queryClient.invalidateQueries({ queryKey: GRID_QUERY_KEY_PREFIX });
    setSituationTarget(null);
  }

  if (profileQuery.isLoading) return <Loader loading variant="page" />;
  if (profileQuery.isError) {
    return <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void profileQuery.refetch()} />;
  }
  if (!canRead) return <EmptyState message="Vous n'avez pas accès à la grille des cotisations." />;

  if (typesQuery.isLoading) return <Loader loading variant="page" />;
  if (typesQuery.isError) {
    return (
      <EmptyState
        variant="error"
        message={apiErrorMessage(typesQuery.error, "Impossible de charger la grille.")}
        actionLabel="Réessayer"
        onAction={() => void typesQuery.refetch()}
      />
    );
  }
  if ((typesQuery.data?.active.length ?? 0) === 0) {
    return (
      <EmptyState
        message="Aucun type de cotisation."
        description="Les types se créent depuis le tableau de bord de la trésorerie."
        actionLabel={canWrite ? "Aller à la trésorerie" : undefined}
        onAction={canWrite ? () => navigate("/tresorerie") : undefined}
      />
    );
  }

  const clubName = profileQuery.data?.club.name ?? auth.club?.name ?? "";
  const gridLoading = gridQuery.isLoading || selectedTypeId === null;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">Grille des cotisations</h1>
          <p className="text-sm text-text-muted">
            {clubName} · {year}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Visibilité basée sur `can_record_payments` : l'API n'expose pas
              de capacité dédiée à l'import et `CONTRIBUTION_IMPORTERS` vaut
              aujourd'hui `PAYMENT_RECORDERS` (services.py, décision par
              défaut de la fiche d'écran §11 point 1). */}
          {canRecordPayments ? (
            <Button variant="secondary" size="sm" onClick={() => setImportOpen(true)}>
              Importer (CSV)
            </Button>
          ) : null}
          <Button
            variant="secondary"
            size="sm"
            loading={exporting}
            loadingLabel="Export…"
            disabled={selectedTypeId === null || !gridQuery.data}
            onClick={() => void handleExport()}
          >
            Exporter (CSV)
          </Button>
        </div>
      </header>

      <div className="sticky top-0 z-[5] space-y-2 rounded-md border border-border bg-surface px-3 py-2">
        <TypeChips
          active={typesQuery.data?.active ?? []}
          archived={typesQuery.data?.archived ?? []}
          selectedTypeId={selectedTypeId}
          onSelect={setSelectedTypeId}
        />
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1">
            <button
              type="button"
              aria-label="Année précédente"
              onClick={() => setYear((y) => y - 1)}
              className="flex h-10 w-10 items-center justify-center rounded-sm text-text hover:bg-surface-muted"
            >
              ‹
            </button>
            <span className="w-14 text-center text-sm font-medium tabular-nums text-text">{year}</span>
            <button
              type="button"
              aria-label="Année suivante"
              onClick={() => setYear((y) => y + 1)}
              className="flex h-10 w-10 items-center justify-center rounded-sm text-text hover:bg-surface-muted"
            >
              ›
            </button>
          </div>
          <SegmentedControl
            label="Filtre"
            value={filterMode}
            onChange={setFilterMode}
            options={[
              { value: "all", label: "Tous" },
              { value: "unpaid", label: "Avec impayés" },
            ]}
          />
        </div>
        <div className="relative">
          <input
            type="search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Rechercher un joueur"
            aria-label="Rechercher un joueur"
            className="h-control-sm w-full rounded-sm border border-border-strong bg-surface px-3 text-sm text-text placeholder:text-text-muted sm:w-64"
          />
        </div>
      </div>

      {!helpDismissed ? (
        <div className="flex items-center justify-between gap-2 rounded-md bg-surface-muted px-3 py-2 text-xs text-text-muted sm:hidden">
          <span>Faites défiler vers la droite pour voir les autres mois, ou tournez votre téléphone.</span>
          <button
            type="button"
            onClick={() => setHelpDismissed(true)}
            aria-label="Fermer l'aide"
            className="shrink-0 text-text-muted hover:text-text"
          >
            ×
          </button>
        </div>
      ) : null}

      <GridLegend currency={currency} />

      {gridQuery.isError ? (
        <EmptyState
          variant="error"
          message={apiErrorMessage(gridQuery.error, "Impossible de charger la grille.")}
          actionLabel="Réessayer"
          onAction={() => void gridQuery.refetch()}
        />
      ) : (
        <DataTable
          key={`${selectedTypeId ?? "none"}-${year}`}
          columns={columns}
          rows={filteredRows}
          getRowId={(row) => row.membership_id}
          loading={gridLoading}
          stickyFirstColumn
          variant="grid"
          pageSize={50}
          resultLabel="joueurs"
          scrollToColumnKey={scrollToColumnKey}
          scrollAreaClassName="max-h-[60dvh] overflow-y-auto"
          emptyState={buildEmptyState()}
        />
      )}

      <MonthDetailModal
        target={monthDetailTarget}
        currency={currency}
        onClose={() => setMonthDetailTarget(null)}
        onPaymentRecorded={handleMonthPaymentRecorded}
      />
      <FinancialSituationModal
        target={situationTarget}
        currency={currency}
        canRecordPayments={canRecordPayments}
        onClose={() => setSituationTarget(null)}
        onPaymentRecorded={handleSituationPaymentRecorded}
      />
      {canRecordPayments ? (
        <ImportContributionsModal
          open={importOpen}
          currency={currency}
          initialTypeId={selectedTypeId}
          initialYear={year}
          onClose={() => setImportOpen(false)}
          onImported={(result) => {
            setSelectedTypeId(result.typeId);
            setYear(result.year);
          }}
        />
      ) : null}
    </div>
  );
}
