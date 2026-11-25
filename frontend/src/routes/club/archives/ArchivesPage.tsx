import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  listArchivedDocuments,
  type ArchiveCategory,
  type ArchivedDocument,
} from "../../../api/assemblies";
import { getMyProfile } from "../../../api/clubs";
import {
  Banner,
  Button,
  EmptyState,
  IconDocumentImage,
  IconDocumentPdf,
  IconNavArchives,
  IconUpload,
  SegmentedControl,
  Skeleton,
  StatusBadge,
  useClubBranding,
  useToast,
} from "../../../design-system";
import { useMediaQuery } from "../../../hooks/useMediaQuery";
import { ArchiveDetailModal } from "./ArchiveDetailModal";
import { ArchiveUploadModal } from "./ArchiveUploadModal";
import { getArchivesAccess } from "./archivesAccess";
import {
  CATEGORY_FILTERS,
  CATEGORY_LABELS,
  categoryFromUrl,
  categoryToUrl,
  formatDocumentDate,
  isImageFileName,
} from "./archivesFormat";

const PAGE_SIZE = 10;
/** L'API n'expose pas la liste des années : les 6 dernières années sont proposées (point ouvert). */
const YEAR_SPAN = 6;

function yearOptions(selected: string): string[] {
  const current = new Date().getFullYear();
  const years = Array.from({ length: YEAR_SPAN }, (_, i) => String(current - i));
  if (selected && !years.includes(selected)) years.push(selected);
  return years;
}

function DocumentRow({ document, onOpen }: { document: ArchivedDocument; onOpen: () => void }) {
  const Icon = isImageFileName(document.file_name) ? IconDocumentImage : IconDocumentPdf;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex min-h-14 w-full items-center gap-3 border-b border-border px-1 py-2 text-left last:border-b-0 hover:bg-surface-muted"
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm bg-surface-muted text-text-muted">
        <Icon aria-hidden="true" className="h-5 w-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span
          className="block break-words text-sm font-medium text-text"
          style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}
        >
          {document.title}
        </span>
        <span className="block text-[13px] text-text-muted">
          {CATEGORY_LABELS[document.category]} · {formatDocumentDate(document.document_date)}
        </span>
      </span>
      {document.status === "withdrawn" ? <StatusBadge status="withdrawn" /> : null}
    </button>
  );
}

const selectClass =
  "h-control-sm w-full rounded-sm border border-border-strong bg-surface px-2 text-sm text-text disabled:opacity-60";

/** Page « Archives » (docs/ecrans/club-archives.md ; CDC 4.15.1). */
export function ArchivesPage() {
  const branding = useClubBranding();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const isWide = useMediaQuery("(min-width: 640px)");
  const [params, setParams] = useSearchParams();
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [replacing, setReplacing] = useState<ArchivedDocument | null>(null);
  const [openDoc, setOpenDoc] = useState<ArchivedDocument | null>(null);

  const category = categoryFromUrl(params.get("categorie"));
  const year = /^\d{4}$/.test(params.get("annee") ?? "") ? (params.get("annee") as string) : "";
  const showWithdrawnRequested = params.get("retires") === "1";

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const access = getArchivesAccess(profileQuery.data?.roles);
  const includeWithdrawn = access.canRead && showWithdrawnRequested;
  const online = typeof navigator === "undefined" ? true : navigator.onLine;

  const listQuery = useQuery({
    queryKey: ["assemblies", "archive", "list", category, year, includeWithdrawn, limit],
    queryFn: () =>
      listArchivedDocuments({
        category: category || undefined,
        year: year || undefined,
        includeWithdrawn,
        limit,
      }),
    enabled: access.canRead,
    placeholderData: keepPreviousData,
  });

  const filtersActive = category !== "" || year !== "";

  function updateParam(key: string, value: string): void {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
    setLimit(PAGE_SIZE);
  }

  function clearFilters(): void {
    const next = new URLSearchParams(params);
    next.delete("categorie");
    next.delete("annee");
    setParams(next, { replace: true });
    setLimit(PAGE_SIZE);
  }

  function invalidate(): void {
    void queryClient.invalidateQueries({ queryKey: ["assemblies", "archive"] });
  }

  function handleSaved(created: ArchivedDocument): void {
    setUploadOpen(false);
    setReplacing(null);
    setOpenDoc(null);
    invalidate();
    const matchesFilters =
      (category === "" || created.category === category) &&
      (year === "" || created.document_date.startsWith(year));
    if (!matchesFilters) {
      showToast("Document déposé dans les archives. Il n'apparaît pas avec les filtres actuels.", {
        actionLabel: "Effacer les filtres",
        onAction: clearFilters,
      });
    }
  }

  const header = (
    <header className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <h1 className="text-xl font-semibold text-text">Archives</h1>
        <p className="text-sm text-text-muted">
          {branding?.name ?? ""}
          {access.canRead && listQuery.data && !filtersActive && !includeWithdrawn
            ? ` · ${listQuery.data.count} document(s)`
            : ""}
        </p>
      </div>
      {access.canWrite ? (
        <Button
          variant="primary"
          size="sm"
          disabled={!online}
          icon={<IconUpload aria-hidden="true" className="h-4 w-4" />}
          onClick={() => setUploadOpen(true)}
        >
          Déposer un document
        </Button>
      ) : null}
    </header>
  );

  if (profileQuery.isLoading) {
    return (
      <div className="mx-auto max-w-[800px] space-y-4">
        {header}
        <Skeleton variant="card" />
      </div>
    );
  }

  if (!access.canRead) {
    return (
      <div className="mx-auto max-w-[800px] space-y-4">
        {header}
        <EmptyState
          variant="error"
          message="Vous n'avez pas accès à cette page."
          description="Les archives sont réservées aux membres du Bureau."
        />
      </div>
    );
  }

  const results = listQuery.data?.results ?? [];
  const total = listQuery.data?.count ?? 0;

  return (
    <div className="mx-auto max-w-[800px] space-y-4">
      {header}
      {!online ? <Banner variant="info">Vous êtes hors connexion. Les documents déjà chargés restent lisibles.</Banner> : null}

      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-text">Documents</h2>
          {listQuery.data ? (
            <span className="text-[13px] text-text-muted">
              {results.length} sur {total}
            </span>
          ) : null}
        </div>

        <div className="mt-3 flex flex-wrap items-end gap-3">
          {isWide ? (
            <SegmentedControl<ArchiveCategory | "">
              label="Catégorie"
              value={category}
              onChange={(v) => updateParam("categorie", categoryToUrl(v))}
              options={CATEGORY_FILTERS.map((f) => ({ value: f.value, label: f.label }))}
            />
          ) : (
            <div className="min-w-0 flex-1">
              <label htmlFor="archive-category" className="mb-1 block text-[13px] font-medium text-text">
                Catégorie
              </label>
              <select
                id="archive-category"
                className={selectClass}
                value={category}
                onChange={(e) => updateParam("categorie", categoryToUrl(e.target.value as ArchiveCategory | ""))}
              >
                {CATEGORY_FILTERS.map((f) => (
                  <option key={f.urlValue} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="min-w-0 flex-1 sm:max-w-48">
            <label htmlFor="archive-year" className="mb-1 block text-[13px] font-medium text-text">
              Année
            </label>
            <select
              id="archive-year"
              className={selectClass}
              value={year}
              onChange={(e) => updateParam("annee", e.target.value)}
            >
              <option value="">Toutes les années</option>
              {yearOptions(year).map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            {filtersActive ? (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                Effacer les filtres
              </Button>
            ) : null}
            {listQuery.data ? <span className="text-[13px] text-text-muted">{total} document(s)</span> : null}
          </div>
          {access.canRead ? (
            <Button variant="ghost" size="sm" onClick={() => updateParam("retires", includeWithdrawn ? "" : "1")}>
              {includeWithdrawn ? "Masquer les documents retirés" : "Afficher les documents retirés"}
            </Button>
          ) : null}
        </div>

        <div className="mt-2">
          {listQuery.isPending ? (
            <div className="space-y-2" aria-busy="true">
              {Array.from({ length: 5 }, (_, i) => (
                <Skeleton key={i} variant="row" />
              ))}
            </div>
          ) : listQuery.isError ? (
            <EmptyState
              variant="error"
              message="Impossible de charger les archives."
              actionLabel="Réessayer"
              onAction={() => void listQuery.refetch()}
            />
          ) : results.length > 0 ? (
            <>
              {results.map((doc) => (
                <DocumentRow key={doc.id} document={doc} onOpen={() => setOpenDoc(doc)} />
              ))}
              {listQuery.data?.next_offset !== null ? (
                <Button
                  variant="secondary"
                  size="sm"
                  className="mt-2"
                  loading={listQuery.isFetching}
                  loadingLabel="Chargement…"
                  onClick={() => setLimit((n) => n + PAGE_SIZE)}
                >
                  Voir plus
                </Button>
              ) : null}
            </>
          ) : filtersActive ? (
            <EmptyState
              variant="no-results"
              message="Aucun document ne correspond à ces filtres."
              actionLabel="Effacer les filtres"
              onAction={clearFilters}
            />
          ) : (
            <EmptyState
              icon={<IconNavArchives aria-hidden="true" className="h-6 w-6 text-text-muted" strokeWidth={1.5} />}
              message="Aucun document archivé pour l'instant."
              description={
                access.canWrite
                  ? "Déposez ici les PV de réunion, les lettres de convocation et les autres documents officiels du club."
                  : "Le Secrétaire dépose les documents officiels du club."
              }
              actionLabel={access.canWrite && online ? "Déposer un document" : undefined}
              onAction={access.canWrite && online ? () => setUploadOpen(true) : undefined}
            />
          )}
        </div>
      </section>

      {openDoc ? (
        <ArchiveDetailModal
          summary={openDoc}
          canWrite={access.canWrite}
          onClose={() => setOpenDoc(null)}
          onChanged={invalidate}
          onReplace={(doc) => {
            setOpenDoc(null);
            setReplacing(doc);
          }}
        />
      ) : null}
      {uploadOpen ? <ArchiveUploadModal onClose={() => setUploadOpen(false)} onDone={handleSaved} /> : null}
      {replacing ? (
        <ArchiveUploadModal replacing={replacing} onClose={() => setReplacing(null)} onDone={handleSaved} />
      ) : null}
    </div>
  );
}
