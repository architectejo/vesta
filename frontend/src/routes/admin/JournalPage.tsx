import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { searchAccounts } from "../../api/auth";
import { exportAuditLogs, listAuditActionTypes, listAuditLogs } from "../../api/audit";
import type { AuditLogFilters, AuditLogLine } from "../../api/audit";
import { listLicences } from "../../api/licences";
import { triggerBlobDownload } from "../../api/client";
import { ApiError } from "../../api/client";
import {
  Button,
  Checkbox,
  ClubSearch,
  EmptyState,
  IconDownload,
  IconFilter,
  IconWarning,
  Loader,
  Modal,
  PlayerSearch,
} from "../../design-system";
import type { ClubSearchResult, PlayerSearchResult } from "../../design-system";
import { actionLabel } from "./actionLabels";
import { JournalEntryModal } from "./JournalEntryModal";
import { formatInZone, formatUtc } from "./journalFormat";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

async function searchClubsForFilter(query: string): Promise<ClubSearchResult[]> {
  // Aucun point d'accès de liste de clubs : la liste des licences en tient lieu (Superuser).
  const licences = await listLicences();
  const needle = query.trim().toLowerCase();
  const seen = new Set<number>();
  const results: ClubSearchResult[] = [];
  for (const licence of licences) {
    if (seen.has(licence.club_id)) continue;
    if (!licence.club_name.toLowerCase().includes(needle)) continue;
    seen.add(licence.club_id);
    results.push({ id: licence.club_id, name: licence.club_name });
  }
  return results;
}

async function searchActors(query: string): Promise<PlayerSearchResult[]> {
  const accounts = await searchAccounts({ query });
  return accounts.map((a) => ({
    id: a.id,
    firstName: a.first_name,
    lastName: a.last_name,
  }));
}

function ActionTypesModal({
  selected,
  onApply,
  onClose,
}: {
  selected: string[];
  onApply: (types: string[]) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<string[]>(selected);
  const query = useQuery({ queryKey: ["audit-action-types"], queryFn: listAuditActionTypes });

  function toggle(type: string, checked: boolean): void {
    setDraft((current) => (checked ? [...current, type] : current.filter((t) => t !== type)));
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Types d'action"
      size="md"
      loading={query.isLoading}
      confirmLabel="Appliquer"
      onConfirm={() => onApply(draft)}
    >
      {query.isError ? (
        <EmptyState variant="error" actionLabel="Réessayer" onAction={() => void query.refetch()} />
      ) : (query.data?.results.length ?? 0) === 0 ? (
        <EmptyState message="Aucun type d'action." />
      ) : (
        <ul className="space-y-2">
          {query.data?.results.map((item) => (
            <li key={item.action_type}>
              <Checkbox
                checked={draft.includes(item.action_type)}
                onChange={(checked) => toggle(item.action_type, checked)}
                label={
                  <>
                    {actionLabel(item.action_type)}
                    {item.is_alert ? <span className="ml-1 text-xs text-status-warning-fg">(alerte)</span> : null}
                  </>
                }
              />
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

const DATE_INPUT_CLASS =
  "h-control-sm w-full rounded-sm border bg-surface px-2 text-sm text-text border-border-strong";

/** Écran « Journal d'activité » (superuser-espace.md §3.4, CDC 5.5) : lecture seule. */
export function JournalPage() {
  const [club, setClub] = useState<ClubSearchResult | null>(null);
  const [actor, setActor] = useState<PlayerSearchResult | null>(null);
  const [actionTypes, setActionTypes] = useState<string[]>([]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [alertsOnly, setAlertsOnly] = useState(false);
  const [typesOpen, setTypesOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const filters: AuditLogFilters = {
    club_id: club?.id ?? null,
    actor_id: actor ? Number(actor.id) : null,
    action_type: actionTypes,
    date_from: DATE_RE.test(dateFrom) ? dateFrom : undefined,
    date_to: DATE_RE.test(dateTo) ? dateTo : undefined,
    alerts_only: alertsOnly,
  };

  const query = useInfiniteQuery({
    queryKey: ["audit-logs", filters],
    queryFn: ({ pageParam }) => listAuditLogs(filters, pageParam),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
  });

  const rows: AuditLogLine[] = query.data?.pages.flatMap((p) => p.results) ?? [];
  const total = query.data?.pages[0]?.count ?? 0;
  const hasFilters =
    club !== null ||
    actor !== null ||
    actionTypes.length > 0 ||
    dateFrom !== "" ||
    dateTo !== "" ||
    alertsOnly;

  const clearFilters = useCallback(() => {
    setClub(null);
    setActor(null);
    setActionTypes([]);
    setDateFrom("");
    setDateTo("");
    setAlertsOnly(false);
  }, []);

  async function handleExport(): Promise<void> {
    setExporting(true);
    setExportError(null);
    try {
      const { blob, filename } = await exportAuditLogs(filters);
      triggerBlobDownload(blob, filename);
    } catch (error) {
      setExportError(error instanceof ApiError ? error.detail : "L'export a échoué. Réessayez.");
    } finally {
      setExporting(false);
    }
  }

  const queryError = query.error instanceof ApiError && query.error.status === 400 ? query.error.detail : null;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-text">Journal d'activité</h1>
          <p className="text-sm text-text">
            Le journal est en ajout seul : aucune entrée ne peut être modifiée ni supprimée.
          </p>
          <p className="text-[13px] text-text-muted">
            Conservation minimale : 5 ans pour les finances, 2 ans pour le reste. Aucune entrée n'est supprimée
            automatiquement.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          icon={<IconDownload className="h-4 w-4" aria-hidden="true" />}
          loading={exporting}
          loadingLabel="Export…"
          onClick={() => void handleExport()}
        >
          Exporter (CSV)
        </Button>
      </header>
      {exportError ? (
        <p role="alert" className="text-sm text-status-danger-fg">
          {exportError}
        </p>
      ) : null}

      <section aria-label="Filtres" className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <p className="mb-1 text-xs text-text-muted">Club</p>
          <ClubSearch value={club} onChange={setClub} searchClubs={searchClubsForFilter} ariaLabel="Club" />
        </div>
        <div>
          <p className="mb-1 text-xs text-text-muted">Acteur</p>
          <PlayerSearch
            value={actor}
            onChange={setActor}
            searchPlayers={searchActors}
            placeholder="Nom ou email de l'acteur"
            ariaLabel="Acteur"
          />
        </div>
        <div>
          <p className="mb-1 text-xs text-text-muted">Type d'action</p>
          <Button
            variant="secondary"
            size="sm"
            icon={<IconFilter className="h-4 w-4" aria-hidden="true" />}
            onClick={() => setTypesOpen(true)}
          >
            {actionTypes.length > 0 ? `Types d'action (${actionTypes.length})` : "Tous les types"}
          </Button>
        </div>
        <label className="block text-xs text-text-muted">
          Du
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className={DATE_INPUT_CLASS}
          />
        </label>
        <label className="block text-xs text-text-muted">
          Au
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className={DATE_INPUT_CLASS} />
        </label>
        <div className="flex items-end">
          <Checkbox checked={alertsOnly} onChange={setAlertsOnly} label="Alertes seulement" />
        </div>
      </section>

      {query.isLoading ? (
        <Loader loading variant="list" count={10} onRetry={() => void query.refetch()} />
      ) : query.isError ? (
        <EmptyState
          variant="error"
          message={queryError ?? undefined}
          actionLabel="Réessayer"
          onAction={() => void query.refetch()}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          variant="no-results"
          message="Aucune entrée pour ces filtres."
          actionLabel={hasFilters ? "Effacer les filtres" : undefined}
          onAction={hasFilters ? clearFilters : undefined}
        />
      ) : (
        <>
          <p className="text-xs text-text-muted">
            {total} {total > 1 ? "entrées" : "entrée"}
          </p>
          <ul className="divide-y divide-border rounded-md border border-border">
            {rows.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(row.id)}
                  className="block w-full px-3 py-2 text-left hover:bg-surface-muted"
                >
                  <span className="flex flex-wrap items-center justify-between gap-x-2 text-xs text-text-muted">
                    <time dateTime={row.created_at} title={formatUtc(row.created_at)}>
                      {formatInZone(row.created_at, row.club_timezone)}
                    </time>
                    <span>{row.club_name ?? "—"}</span>
                  </span>
                  <span className="mt-0.5 flex flex-wrap items-center gap-1 text-sm font-medium text-text">
                    {row.is_alert ? (
                      <IconWarning
                        className="h-4 w-4 text-status-warning-fg"
                        aria-label="Alerte"
                        role="img"
                      />
                    ) : null}
                    {actionLabel(row.action_type)}
                  </span>
                  <span className="block text-sm text-text">
                    {row.actor_display}
                    {row.acted_as_ghost ? " (support)" : ""}
                  </span>
                  <span className="block break-words text-xs text-text-muted">
                    {row.object_type} #{row.object_id}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {query.hasNextPage ? (
            <div className="flex justify-center">
              <Button
                variant="secondary"
                size="sm"
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

      {typesOpen ? (
        <ActionTypesModal
          selected={actionTypes}
          onClose={() => setTypesOpen(false)}
          onApply={(types) => {
            setActionTypes(types);
            setTypesOpen(false);
          }}
        />
      ) : null}
      {selectedId !== null ? <JournalEntryModal logId={selectedId} onClose={() => setSelectedId(null)} /> : null}
    </div>
  );
}
