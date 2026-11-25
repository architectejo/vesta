import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, triggerBlobDownload } from "../../api/client";
import {
  createContributionImport,
  downloadContributionImportReport,
  getGridContributionTypes,
  previewContributionImport,
  type ContributionImportReport,
  type ContributionImportRow,
} from "../../api/treasury";
import {
  Avatar,
  Banner,
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
  IconButton,
  IconChevronLeft,
  IconChevronRight,
  Loader,
  Modal,
  SegmentedControl,
  StatusBadge,
  useToast,
  type DataTableColumn,
} from "../../design-system";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { cellVisual } from "./gridCellVisuals";
import { ImportRowDetailModal } from "./ImportRowDetailModal";
import { formatAmount, formatNumber } from "./money";

const TYPES_QUERY_KEY = ["treasury", "grid-types"] as const;
const MIN_YEAR = 2000;
const SEARCH_THRESHOLD = 30;
const ROWS_PAGE_SIZE = 20;

// Modèle vide dérivé de la docstring de `preview_contribution_import` /
// `import_contributions` (backend/apps/treasury/services.py, section
// « Import des cotisations historiques CSV ») : l'Annexe C, partie 4
// (formats CSV, CDC 10.1) reste à rédiger séparément (voir compte rendu).
const CSV_TEMPLATE_HEADER = "email;nom;janv.;févr.;mars;avr.;mai;juin;juil.;août;sept.;oct.;nov.;déc.\n";

function downloadCsvTemplate(): void {
  const blob = new Blob([CSV_TEMPLATE_HEADER], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "modele-import-cotisations.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.detail
    : "Une erreur est survenue de notre côté. Réessayez dans un instant.";
}

function rowDisplayName(row: ContributionImportRow): string {
  return row.player ? `${row.player.first_name} ${row.player.last_name}`.trim() : row.identity;
}

function formatFileSize(file: File): string {
  return `${Math.max(1, Math.round(file.size / 1024))} Ko`;
}

type Step = 1 | 2 | 3;
type PreviewTab = "failed" | "ready" | "grid";

interface SummaryGridProps {
  report: ContributionImportReport;
  currency: string;
  succeededLabel: string;
}

function SummaryGrid({ report, currency, succeededLabel }: SummaryGridProps) {
  const { summary } = report;
  return (
    <div className="grid grid-cols-2 gap-3 rounded-md border border-border p-3 md:grid-cols-4">
      <div>
        <p className="text-lg font-semibold tabular-nums text-text">{summary.rows_total}</p>
        <p className="text-xs text-text-muted">Lignes lues</p>
      </div>
      <div>
        <p className="text-lg font-semibold tabular-nums text-status-success-fg">{summary.rows_succeeded}</p>
        <p className="text-xs text-text-muted">{succeededLabel}</p>
      </div>
      <div>
        <p
          className={[
            "text-lg font-semibold tabular-nums",
            summary.rows_failed > 0 ? "text-status-danger-fg" : "text-text",
          ].join(" ")}
        >
          {summary.rows_failed}
        </p>
        <p className="text-xs text-text-muted">Lignes en échec</p>
      </div>
      <div>
        <p className="text-lg font-semibold tabular-nums text-text">{summary.payments_count}</p>
        <p className="text-xs text-text-muted">
          Paiements à créer · {formatAmount(summary.payments_total, currency)}
        </p>
      </div>
      <div>
        <p className="text-lg font-semibold tabular-nums text-text">{summary.dues_count}</p>
        <p className="text-xs text-text-muted">Montants dus à créer</p>
      </div>
      {summary.already_imported_count > 0 ? (
        <div>
          <p className="text-lg font-semibold tabular-nums text-text">{summary.already_imported_count}</p>
          <p className="text-xs text-text-muted">Déjà importés (ignorés)</p>
        </div>
      ) : null}
    </div>
  );
}

interface FailedRowsListProps {
  rows: ContributionImportRow[];
}

function FailedRowsList({ rows }: FailedRowsListProps) {
  const [visibleCount, setVisibleCount] = useState(ROWS_PAGE_SIZE);
  if (rows.length === 0) return <EmptyState message="Aucune ligne en échec." />;
  const visible = rows.slice(0, visibleCount);
  return (
    <div className="space-y-2">
      {visible.map((row) => (
        <div key={row.line_number} className="rounded-md border border-border p-3">
          <div className="mb-1 flex items-center justify-between gap-2">
            <p className="text-sm font-medium text-text">
              Ligne {row.line_number} · {row.identity}
            </p>
            <StatusBadge status="import_failed" />
          </div>
          {row.errors.map((error, index) => (
            <p key={index} className="text-sm text-status-danger-fg">
              {error}
            </p>
          ))}
        </div>
      ))}
      {visibleCount < rows.length ? (
        <Button size="sm" variant="secondary" onClick={() => setVisibleCount((n) => n + ROWS_PAGE_SIZE)}>
          Voir plus
        </Button>
      ) : null}
    </div>
  );
}

interface ReadyRowsListProps {
  rows: ContributionImportRow[];
  currency: string;
  onOpenRow: (row: ContributionImportRow) => void;
}

function ReadyRowsList({ rows, currency, onOpenRow }: ReadyRowsListProps) {
  const [visibleCount, setVisibleCount] = useState(ROWS_PAGE_SIZE);
  if (rows.length === 0) return <EmptyState message="Aucune ligne n'est prête à être importée." />;
  const visible = rows.slice(0, visibleCount);
  return (
    <div className="space-y-2">
      {visible.map((row) => {
        const name = rowDisplayName(row);
        return (
          <button
            key={row.line_number}
            type="button"
            onClick={() => onOpenRow(row)}
            className="flex w-full items-center gap-3 rounded-md border border-border p-3 text-left hover:bg-surface-muted"
          >
            <Avatar name={name} photoUrl={row.player?.photo ?? null} size={24} />
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium text-text">{name}</span>
              <span className="block text-xs text-text-muted">
                {row.payments.length} paiement(s) ·{" "}
                {formatAmount(
                  row.payments.reduce((sum, line) => sum + Number(line.amount), 0),
                  currency,
                )}{" "}
                · solde {row.balance_before !== null ? formatAmount(row.balance_before, currency) : "—"} →{" "}
                {row.balance_after !== null ? formatAmount(row.balance_after, currency) : "—"}
              </span>
            </span>
            <StatusBadge status={row.warnings.length > 0 ? "import_to_check" : "import_ready"} />
          </button>
        );
      })}
      {visibleCount < rows.length ? (
        <Button size="sm" variant="secondary" onClick={() => setVisibleCount((n) => n + ROWS_PAGE_SIZE)}>
          Voir plus
        </Button>
      ) : null}
    </div>
  );
}

interface GridTabProps {
  rows: ContributionImportRow[];
  months: ContributionImportReport["months"];
  currency: string;
}

function GridTab({ rows, months, currency }: GridTabProps) {
  const gridRows = rows.filter((row) => row.status !== "failed" && row.cells.length > 0);
  const columns = useMemo<Array<DataTableColumn<ContributionImportRow>>>(() => {
    const monthColumns: Array<DataTableColumn<ContributionImportRow>> = months.map((month, index) => ({
      key: `month-${month.month}`,
      header: month.label,
      widthPx: 56,
      render: (row: ContributionImportRow) => {
        const cell = row.cells[index];
        if (!cell) return null;
        const visual = cellVisual(cell);
        return (
          <span
            aria-label={`${month.label} : ${cell.state_label}, ${visual.text}`}
            className={["flex h-9 items-center justify-center gap-1 rounded-sm text-xs tabular-nums", visual.bgClass, visual.textClass].join(" ")}
          >
            {visual.dot}
            <span>{visual.text}</span>
          </span>
        );
      },
    }));
    return [
      {
        key: "player",
        header: "Joueur",
        widthPx: 120,
        render: (row: ContributionImportRow) => (
          <span className="flex items-center gap-2">
            <Avatar name={rowDisplayName(row)} photoUrl={row.player?.photo ?? null} size={24} />
            <span className="truncate text-sm text-text">{rowDisplayName(row)}</span>
          </span>
        ),
      },
      ...monthColumns,
      {
        key: "total",
        header: "Total",
        widthPx: 72,
        align: "right",
        render: (row: ContributionImportRow) => (
          <span className="tabular-nums text-text">{row.total !== null ? formatNumber(row.total) : "—"}</span>
        ),
      },
    ];
  }, [months]);

  return (
    <div className="space-y-2">
      <p className="text-xs text-text-muted">
        Grille telle qu'elle sera après l'import. La répartition suit la règle du club : les mois impayés les
        plus anciens sont couverts en premier.
      </p>
      <DataTable
        columns={columns}
        rows={gridRows}
        getRowId={(row) => row.line_number}
        stickyFirstColumn
        variant="grid"
        resultLabel="joueurs"
        scrollAreaClassName="max-h-[50dvh] overflow-y-auto"
        emptyState={<EmptyState message="Aucune ligne n'est prête à être importée." />}
      />
      {currency ? <p className="text-xs text-text-muted">Montants en {currency}.</p> : null}
    </div>
  );
}

export interface ImportContributionsModalProps {
  open: boolean;
  currency: string;
  /** Type affiché sur la grille au moment de l'ouverture (vide s'il n'est pas importable, §3). */
  initialTypeId?: number | null;
  initialYear: number;
  onClose: () => void;
  /** Après un import réussi (invalidation des listes de la page appelante, année affichée). */
  onImported: (result: { typeId: number; year: number; paymentsCount: number }) => void;
}

/**
 * Modale « Importer les cotisations » (fiche
 * `docs/ecrans/tresorerie-import-cotisations.md`, CDC 4.4.8). Trois étapes :
 * fichier, aperçu, résultat. Aucune règle métier ici : l'analyse du fichier,
 * la recherche des joueurs, les paiements et montants dus prévus, les
 * soldes viennent entièrement du rapport renvoyé par l'API.
 */
export function ImportContributionsModal({
  open,
  currency,
  initialTypeId,
  initialYear,
  onClose,
  onImported,
}: ImportContributionsModalProps) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();

  const [step, setStep] = useState<Step>(1);
  const [typeId, setTypeId] = useState<number | "">("");
  const [year, setYear] = useState(initialYear);
  const [file, setFile] = useState<File | null>(null);
  const [formatHelpOpen, setFormatHelpOpen] = useState(false);

  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ContributionImportReport | null>(null);

  const [tab, setTab] = useState<PreviewTab>("ready");
  const [rowSearchInput, setRowSearchInput] = useState("");
  const debouncedRowSearch = useDebouncedValue(rowSearchInput, 300);
  const [rowDetail, setRowDetail] = useState<ContributionImportRow | null>(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [importSubmitting, setImportSubmitting] = useState(false);
  const [step2Banner, setStep2Banner] = useState<{ variant: "danger" | "warning"; message: string; retry?: boolean } | null>(
    null,
  );

  const [result, setResult] = useState<ContributionImportReport | null>(null);
  const [reportDownloading, setReportDownloading] = useState(false);

  const currentYear = new Date().getFullYear();

  const typesQuery = useQuery({
    queryKey: TYPES_QUERY_KEY,
    queryFn: () => getGridContributionTypes(),
    enabled: open,
  });

  const importableTypes = useMemo(
    () => (typesQuery.data?.active ?? []).filter((type) => type.is_free || type.periodicity === "monthly"),
    [typesQuery.data],
  );

  // Réinitialisation complète à chaque fermeture (§4 de la fiche).
  useEffect(() => {
    if (open) return;
    setStep(1);
    setTypeId("");
    setYear(initialYear);
    setFile(null);
    setFormatHelpOpen(false);
    setPreviewLoading(false);
    setPreviewError(null);
    setPreview(null);
    setTab("ready");
    setRowSearchInput("");
    setRowDetail(null);
    setConfirmOpen(false);
    setImportSubmitting(false);
    setStep2Banner(null);
    setResult(null);
    setReportDownloading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Type et année de la grille préremplis à l'ouverture ; champ « Type »
  // vide si le type affiché n'est pas importable (§3 de la fiche).
  useEffect(() => {
    if (!open || typesQuery.isLoading) return;
    if (initialTypeId != null && importableTypes.some((type) => type.id === initialTypeId)) {
      setTypeId(initialTypeId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, typesQuery.isLoading, importableTypes]);

  const isDirty = step !== 3 && file !== null;

  async function runInitialPreview(): Promise<void> {
    if (!file || typeId === "") return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const report = await previewContributionImport({ contribution_type_id: Number(typeId), year, file });
      setPreview(report);
      setTab(report.summary.rows_failed > 0 ? "failed" : "ready");
      setRowSearchInput("");
      setStep(2);
    } catch (error) {
      setPreviewError(apiErrorMessage(error));
    } finally {
      setPreviewLoading(false);
    }
  }

  async function relaunchPreviewFromStep2(): Promise<void> {
    if (!file || typeId === "") return;
    setPreviewLoading(true);
    setStep2Banner(null);
    try {
      const report = await previewContributionImport({ contribution_type_id: Number(typeId), year, file });
      setPreview(report);
      setTab(report.summary.rows_failed > 0 ? "failed" : "ready");
    } catch (error) {
      setStep2Banner({ variant: "danger", message: apiErrorMessage(error) });
    } finally {
      setPreviewLoading(false);
    }
  }

  function handleBackToStep1(): void {
    setStep(1);
    setPreview(null);
    setStep2Banner(null);
  }

  function handleOpenConfirm(): void {
    setStep2Banner(null);
    setConfirmOpen(true);
  }

  async function submitImport(): Promise<void> {
    if (!file || typeId === "") return;
    if (importSubmitting) return;
    setImportSubmitting(true);
    try {
      const report = await createContributionImport({ contribution_type_id: Number(typeId), year, file });
      setConfirmOpen(false);
      setResult(report);
      setTab(report.summary.rows_failed > 0 ? "failed" : "ready");
      setStep(3);
    } catch (error) {
      if (error instanceof ApiError && error.status === 0) {
        setConfirmOpen(false);
        setStep2Banner({
          variant: "warning",
          message:
            "La connexion a été interrompue : l'import a peut-être été enregistré. Relancez l'aperçu : les paiements déjà importés y apparaîtront comme « déjà importés » et ne seront pas recréés.",
          retry: true,
        });
      } else {
        setConfirmOpen(false);
        setStep2Banner({ variant: "danger", message: apiErrorMessage(error) });
      }
    } finally {
      setImportSubmitting(false);
    }
  }

  async function handleDownloadReport(): Promise<void> {
    if (!result?.import_batch_id) return;
    setReportDownloading(true);
    try {
      const { blob, filename } = await downloadContributionImportReport(result.import_batch_id, result.year);
      triggerBlobDownload(blob, filename);
    } catch {
      showToast("Impossible de télécharger le rapport. Réessayez.");
    } finally {
      setReportDownloading(false);
    }
  }

  function handleFinalClose(): void {
    if (result) {
      void queryClient.invalidateQueries({ queryKey: ["treasury"] });
      showToast(`Import terminé : ${result.summary.payments_count} paiement(s) enregistré(s).`);
      onImported({ typeId: Number(typeId), year: result.year, paymentsCount: result.summary.payments_count });
    }
    onClose();
  }

  const activeReport = step === 3 ? result : preview;
  const failedRows = activeReport?.rows.filter((row) => row.status === "failed") ?? [];
  const readyRows = activeReport?.rows.filter((row) => row.status !== "failed") ?? [];

  function matchesSearch(row: ContributionImportRow, needle: string): boolean {
    if (!needle) return true;
    const haystack = `${row.identity} ${rowDisplayName(row)}`.toLowerCase();
    return haystack.includes(needle.toLowerCase());
  }

  const filteredFailedRows = failedRows.filter((row) => matchesSearch(row, debouncedRowSearch));
  const filteredReadyRows = readyRows.filter((row) => matchesSearch(row, debouncedRowSearch));
  const currentTabRowCount = tab === "failed" ? failedRows.length : tab === "ready" ? readyRows.length : 0;

  function typeOptionLabel(type: (typeof importableTypes)[number]): string {
    if (type.is_free) return `${type.name} — libre`;
    return `${type.name} — ${formatAmount(type.amount ?? "0", currency)}`;
  }

  const stepLabel =
    step === 1 ? "Étape 1 sur 3 · Fichier" : step === 2 ? "Étape 2 sur 3 · Aperçu" : "Étape 3 sur 3 · Résultat";

  // --- États particuliers (§9 de la fiche) --------------------------------

  if (typesQuery.isError) {
    return (
      <Modal open={open} onClose={onClose} title="Importer les cotisations" subtitle={stepLabel} size="xl" cancelLabel="Fermer">
        <EmptyState
          variant="error"
          message="Impossible de charger les types de cotisation."
          actionLabel="Réessayer"
          onAction={() => void typesQuery.refetch()}
        />
      </Modal>
    );
  }

  if (!typesQuery.isLoading && importableTypes.length === 0) {
    return (
      <Modal open={open} onClose={onClose} title="Importer les cotisations" subtitle={stepLabel} size="xl" cancelLabel="Fermer">
        <EmptyState
          message="Aucun type de cotisation ne peut être importé."
          description="Seuls les types actifs, mensuels ou libres, peuvent être importés."
        />
      </Modal>
    );
  }

  // --- Étape 1 : fichier ----------------------------------------------------

  if (step === 1) {
    return (
      <Modal
        open={open}
        onClose={onClose}
        title="Importer les cotisations"
        subtitle={stepLabel}
        size="xl"
        isDirty={isDirty}
        confirmLabel="Voir l'aperçu"
        confirmLoadingLabel="Analyse du fichier…"
        isSubmitting={previewLoading}
        confirmDisabled={!file || typeId === "" || previewLoading}
        onConfirm={() => void runInitialPreview()}
      >
        <div className="space-y-4">
          {previewError ? <Banner variant="danger">{previewError}</Banner> : null}

          <div>
            <label className="mb-1 block text-sm font-medium text-text" htmlFor="import-contrib-type">
              Type de cotisation
            </label>
            {typesQuery.isLoading ? (
              <div className="h-control-md w-full animate-pulse rounded-sm bg-skeleton" />
            ) : (
              <select
                id="import-contrib-type"
                className="h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
                value={typeId}
                onChange={(event) => setTypeId(Number(event.target.value))}
              >
                <option value="" disabled>
                  Choisissez un type
                </option>
                {importableTypes.map((type) => (
                  <option key={type.id} value={type.id}>
                    {typeOptionLabel(type)}
                  </option>
                ))}
              </select>
            )}
            <p className="mt-1 text-xs text-text-muted">
              Seuls les types mensuels et les cotisations libres peuvent être importés.
            </p>
          </div>

          <div>
            <p className="mb-1 block text-sm font-medium text-text">Année</p>
            <div className="flex items-center gap-1">
              <IconButton
                aria-label="Année précédente"
                onClick={() => setYear((y) => Math.max(MIN_YEAR, y - 1))}
                disabled={year <= MIN_YEAR}
                icon={<IconChevronLeft aria-hidden="true" className="h-5 w-5" />}
              />
              <span className="w-14 text-center text-sm font-medium tabular-nums text-text">{year}</span>
              <IconButton
                aria-label="Année suivante"
                onClick={() => setYear((y) => Math.min(currentYear, y + 1))}
                disabled={year >= currentYear}
                icon={<IconChevronRight aria-hidden="true" className="h-5 w-5" />}
              />
            </div>
          </div>

          <div>
            <p className="mb-1 block text-sm font-medium text-text">Fichier CSV</p>
            {file ? (
              <div className="flex items-center justify-between gap-2 rounded-md border border-border-strong p-3 text-sm text-text">
                <span>
                  {file.name} · {formatFileSize(file)}
                </span>
                <label className="cursor-pointer font-medium text-primary-text hover:underline">
                  Changer
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    className="sr-only"
                    onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  />
                </label>
              </div>
            ) : (
              <label className="flex min-h-[44px] cursor-pointer items-center justify-center rounded-md border border-dashed border-border-strong p-3 text-sm font-medium text-primary-text hover:bg-surface-muted">
                Choisir un fichier CSV
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="sr-only"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
              </label>
            )}
          </div>

          <details
            open={formatHelpOpen}
            onToggle={(event) => setFormatHelpOpen((event.target as HTMLDetailsElement).open)}
            className="rounded-md border border-border p-3"
          >
            <summary className="cursor-pointer text-sm font-medium text-text">Format attendu</summary>
            <p className="mt-2 text-xs text-text-muted">
              Une ligne par joueur. Une colonne « email » ou « nom » (ou les deux), puis une colonne par mois
              (« janv. », « févr. »… ou « 01/2026 »). Dans une cellule : un montant = paiement de ce montant ;
              « ok » = mois payé au montant plein ; vide, « - » ou « 0 » = rien payé. Les autres colonnes
              (« N° », « Total ») sont ignorées. Fichier enregistré en UTF-8, 500 lignes au plus, 10 Mo au plus.
            </p>
            <button
              type="button"
              onClick={downloadCsvTemplate}
              className="mt-2 text-sm font-medium text-primary-text hover:underline"
            >
              Télécharger un modèle vide
            </button>
          </details>
        </div>
      </Modal>
    );
  }

  // --- Étape 2 : aperçu -------------------------------------------------

  if (step === 2 && preview) {
    const disableImport = preview.summary.rows_succeeded === 0 || preview.summary.payments_count + preview.summary.dues_count === 0;

    return (
      <>
        <Modal
          open={open}
          onClose={onClose}
          title="Importer les cotisations"
          subtitle={stepLabel}
          size="xl"
          isDirty={isDirty}
          isSubmitting={importSubmitting}
          confirmLabel={`Importer ${preview.summary.rows_succeeded} ligne(s)`}
          confirmDisabled={disableImport}
          onConfirm={handleOpenConfirm}
        >
          {importSubmitting ? (
            <div className="space-y-3">
              <Loader loading variant="list" count={3} />
              <p className="text-sm text-text">
                Import en cours. Cela peut prendre jusqu'à une minute : ne fermez pas cette fenêtre.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <Button variant="ghost" size="sm" icon={<IconChevronLeft aria-hidden="true" className="h-4 w-4" />} onClick={handleBackToStep1}>
                Modifier le type, l'année ou le fichier
              </Button>

              <p className="text-sm text-text-muted">
                {preview.contribution_type.name} · {preview.year} · {file?.name}
              </p>

              {step2Banner ? (
                <Banner variant={step2Banner.variant}>
                  <span>
                    {step2Banner.message}
                    {step2Banner.retry ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        className="ml-2"
                        loading={previewLoading}
                        loadingLabel="Analyse…"
                        onClick={() => void relaunchPreviewFromStep2()}
                      >
                        Relancer l'aperçu
                      </Button>
                    ) : null}
                  </span>
                </Banner>
              ) : null}

              <SummaryGrid report={preview} currency={currency} succeededLabel="Lignes prêtes" />

              {preview.ignored_columns.length > 0 ? (
                <Banner variant="info">Colonnes ignorées : {preview.ignored_columns.join(", ")}.</Banner>
              ) : null}
              {preview.ignored_lines.length > 0 ? (
                <Banner variant="info">Lignes ignorées (titre ou ligne vide) : {preview.ignored_lines.join(", ")}.</Banner>
              ) : null}

              <Banner variant="warning">
                Les paiements importés seront enregistrés comme validés, avec un reçu. Ils ne pourront plus être
                supprimés : une erreur se corrige par une annulation.
              </Banner>

              {disableImport ? (
                <Banner variant="info">
                  Rien à importer : aucune ligne ne crée de paiement ni de montant dû.
                </Banner>
              ) : null}

              <SegmentedControl
                label="Détail des lignes"
                value={tab}
                onChange={setTab}
                options={[
                  { value: "failed", label: `En échec (${failedRows.length})` },
                  { value: "ready", label: `Prêtes (${readyRows.length})` },
                  { value: "grid", label: "Grille" },
                ]}
              />

              {tab !== "grid" && currentTabRowCount > SEARCH_THRESHOLD ? (
                <input
                  type="search"
                  value={rowSearchInput}
                  onChange={(event) => setRowSearchInput(event.target.value)}
                  placeholder="Rechercher un joueur"
                  aria-label="Rechercher un joueur"
                  className="h-control-sm w-full rounded-sm border border-border-strong bg-surface px-3 text-sm text-text placeholder:text-text-muted sm:w-64"
                />
              ) : null}

              {tab === "failed" ? <FailedRowsList rows={filteredFailedRows} /> : null}
              {tab === "ready" ? (
                <ReadyRowsList rows={filteredReadyRows} currency={currency} onOpenRow={setRowDetail} />
              ) : null}
              {tab === "grid" ? <GridTab rows={preview.rows} months={preview.months} currency={currency} /> : null}
            </div>
          )}
        </Modal>

        <ConfirmDialog
          open={confirmOpen}
          danger={false}
          title={`Importer ${preview.summary.payments_count} paiement(s) pour ${formatAmount(preview.summary.payments_total, currency)} ?`}
          description={`${preview.summary.dues_count} montant(s) dû(s) seront aussi créés — ${preview.contribution_type.name}, ${preview.year}. Les paiements importés ne pourront plus être supprimés, seulement annulés.`}
          confirmLabel="Importer"
          loadingLabel="Import en cours…"
          loading={importSubmitting}
          onConfirm={() => void submitImport()}
          onCancel={() => setConfirmOpen(false)}
        />

        <ImportRowDetailModal row={rowDetail} currency={currency} onClose={() => setRowDetail(null)} />
      </>
    );
  }

  // --- Étape 3 : résultat -------------------------------------------------

  if (step === 3 && result) {
    return (
      <Modal
        open={open}
        onClose={handleFinalClose}
        title="Importer les cotisations"
        subtitle={stepLabel}
        size="xl"
        footer={<Button onClick={handleFinalClose}>Fermer</Button>}
      >
        <div className="space-y-4">
          <Banner variant="success">Import terminé.</Banner>

          <SummaryGrid report={result} currency={currency} succeededLabel="Lignes importées" />

          {result.import_batch_id ? (
            <Button
              size="sm"
              variant="secondary"
              loading={reportDownloading}
              loadingLabel="Téléchargement…"
              onClick={() => void handleDownloadReport()}
            >
              Télécharger le rapport (CSV)
            </Button>
          ) : null}

          {result.summary.rows_failed > 0 ? (
            <>
              <Banner variant="warning">
                {result.summary.rows_failed} ligne(s) n'ont pas été importées. Corrigez-les dans le fichier puis
                relancez un import : les lignes déjà importées ne seront pas recréées.
              </Banner>
              <FailedRowsList rows={result.rows.filter((row) => row.status === "failed")} />
            </>
          ) : null}
        </div>
      </Modal>
    );
  }

  return null;
}
