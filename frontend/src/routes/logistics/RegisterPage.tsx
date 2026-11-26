import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getMyProfile } from "../../api/clubs";
import {
  downloadRegisterCsv,
  downloadRegisterPdf,
  getRegister,
  type ArticleCategory,
  type RegisterLine,
  type RegisterParams,
  type RegisterSection,
} from "../../api/logistics";
import {
  Button,
  Checkbox,
  DataTable,
  EmptyState,
  IconButton,
  IconChevronLeft,
  IconMore,
  Loader,
  Skeleton,
  FilterChips,
  useToast,
  type DataTableColumn,
} from "../../design-system";
import { useClosingState } from "../../hooks/useClosingState";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { DecommissionDetailModal } from "./DecommissionDetailModal";
import { formatDateFr } from "./format";
import { HolderSearch, type HolderSelection } from "./HolderSearch";
import { getMaterialAccess } from "./materielAccess";
import { ARTICLE_CATEGORY_OPTIONS } from "./materielLabels";
import { MovementDetailModal } from "./MovementDetailModal";
import { OFFLINE_ACTION_MESSAGE, useOnlineStatus } from "./useOnlineStatus";

const SECTION_STEP = 30;

const REGISTER_COLUMNS: Array<DataTableColumn<RegisterLine>> = [
  { key: "designation", header: "Désignation", widthPx: 180, render: (line) => line.designation },
  {
    key: "quantity",
    header: "Quantité",
    align: "right",
    render: (line) => <span className="tabular-nums">{`${line.quantity} ${line.unit}`}</span>,
  },
  { key: "origin", header: "Origine", render: (line) => line.origin },
  { key: "acquisition", header: "Date d'acquisition", render: (line) => line.acquisition_label },
  { key: "location", header: "Localisation", render: (line) => line.location },
  { key: "condition", header: "État actuel", render: (line) => line.condition_display },
];

function SectionCard({
  section,
  isWide,
  onOpenLine,
}: {
  section: RegisterSection;
  isWide: boolean;
  onOpenLine: (movementId: number) => void;
}) {
  const [limit, setLimit] = useState(SECTION_STEP);
  const lines = section.lines.slice(0, limit);
  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
      <h2 className="mb-3 text-base font-semibold text-text">{section.category_display}</h2>
      {isWide ? (
        <DataTable
          columns={REGISTER_COLUMNS}
          rows={lines}
          getRowId={(line) => line.movement_id}
          onRowClick={(line) => onOpenLine(line.movement_id)}
          stickyFirstColumn
          pageSize={100_000}
        />
      ) : (
        <ul className="divide-y divide-border">
          {lines.map((line) => (
            <li key={line.movement_id}>
              <button
                type="button"
                onClick={() => onOpenLine(line.movement_id)}
                className="block min-h-14 w-full py-2 text-left"
              >
                <span className="block text-sm text-text">
                  {line.designation} ·{" "}
                  <span className="tabular-nums">
                    {line.quantity} {line.unit}
                  </span>
                </span>
                <span className="block text-[13px] text-text-muted">
                  {line.origin} · {line.acquisition_label}
                </span>
                <span className="block text-[13px] text-text-muted">
                  chez {line.location} · {line.condition_display}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {section.lines.length > limit ? (
        <div className="mt-2 text-center">
          <Button size="sm" variant="secondary" onClick={() => setLimit((n) => n + SECTION_STEP)}>
            Voir plus
          </Button>
        </div>
      ) : null}
      <div className="mt-3 space-y-1 border-t border-border pt-2 text-sm text-text">
        <p>
          Total :{" "}
          <span className="tabular-nums">
            {section.stock_total_by_unit.map((total) => `${total.quantity} ${total.unit}`).join(" · ") || "0"}
          </span>
        </p>
        {section.current_distribution.length > 0 ? (
          <p>
            Répartition actuelle :{" "}
            {section.current_distribution.map((row) => `Chez ${row.holder_name} ${row.quantity}`).join(" · ")}
          </p>
        ) : null}
        <p className="text-[13px] text-text-muted">
          La localisation de chaque ligne est celle de l'entrée en stock ; la répartition actuelle tient compte des
          déplacements.
        </p>
      </div>
    </section>
  );
}

/** Page « Registre de l'intendance » (spec B4 §4, lot 5). */
export function RegisterPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const isWide = useMediaQuery("(min-width: 768px)");
  const online = useOnlineStatus();

  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput, 300).trim();
  const [category, setCategory] = useState<ArticleCategory | "">("");
  const [holder, setHolder] = useState<HolderSelection | null>(null);
  const [includeExits, setIncludeExits] = useState(false);
  const [downloading, setDownloading] = useState<"pdf" | "csv" | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menu = useClosingState(menuOpen, 200);
  const [movementId, setMovementId] = useState<number | null>(null);
  const [decommissionId, setDecommissionId] = useState<number | null>(null);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const access = getMaterialAccess(profileQuery.data?.roles);

  const params: RegisterParams = useMemo(
    () => ({
      search: search || undefined,
      category: category || undefined,
      holder: holder ? (holder.id ?? "none") : undefined,
      include_exits: includeExits || undefined,
    }),
    [search, category, holder, includeExits],
  );
  const hasFilter = Boolean(params.search || params.category || params.holder !== undefined);

  const registerQuery = useQuery({
    queryKey: ["logistics", "register", params],
    queryFn: () => getRegister(params),
    enabled: access.canReadMaterial,
  });

  // 404 sur le détenteur filtré : filtre remis à zéro (spec §4).
  const holderNotFound =
    registerQuery.error instanceof ApiError && registerQuery.error.status === 404 && params.holder !== undefined;
  useEffect(() => {
    if (!holderNotFound) return;
    setHolder(null);
    showToast("Ce détenteur n'existe pas dans ce club.");
  }, [holderNotFound, showToast]);

  function clearFilters(): void {
    setSearchInput("");
    setCategory("");
    setHolder(null);
  }

  async function handleDownload(format: "pdf" | "csv"): Promise<void> {
    setMenuOpen(false);
    setDownloading(format);
    try {
      if (format === "pdf") await downloadRegisterPdf(params);
      else await downloadRegisterCsv(params);
    } catch {
      showToast("Le registre n'a pas pu être généré. Réessayez.");
    } finally {
      setDownloading(null);
    }
  }

  if (profileQuery.isLoading) return <Loader loading variant="page" />;
  if (!access.canReadMaterial) {
    return <EmptyState message="Vous n'avez pas accès à cette page." />;
  }

  const register = registerQuery.data;
  const offlineHint = online ? undefined : OFFLINE_ACTION_MESSAGE;

  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <Link to="/materiel" className="inline-flex min-h-control-sm items-center gap-1 text-sm font-medium text-primary-text hover:underline">
          <IconChevronLeft aria-hidden="true" className="h-4 w-4" />
          Matériel
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-text">Registre de l'intendance</h1>
            {register ? (
              <p className="text-sm text-text-muted">
                {register.club.name} · arrêté au {formatDateFr(register.as_of)}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              disabled={!online || downloading !== null}
              loading={downloading === "pdf"}
              loadingLabel="Préparation du PDF…"
              title={offlineHint}
              onClick={() => void handleDownload("pdf")}
            >
              Télécharger (PDF)
            </Button>
            <div className="relative">
              <IconButton
                aria-label="Plus d'actions"
                onClick={() => setMenuOpen((v) => !v)}
                icon={<IconMore aria-hidden="true" className="h-5 w-5" />}
              />
              {menu.mounted ? (
                <div
                  data-state={menu.dataState}
                  onAnimationEnd={menu.onAnimationEnd}
                  className="vesta-anim-menu absolute right-0 z-20 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated"
                >
                  <button
                    type="button"
                    disabled={!online || downloading !== null}
                    className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted disabled:opacity-60"
                    onClick={() => void handleDownload("csv")}
                  >
                    {downloading === "csv" ? "Préparation du fichier…" : "Exporter (CSV)"}
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </div>
        {downloading === "csv" ? <p className="text-[13px] text-text-muted">Préparation du fichier…</p> : null}
        {offlineHint ? <p className="text-[13px] text-text-muted">{offlineHint}</p> : null}
        {register?.filters_label ? (
          <p className="text-[13px] text-text-muted">Extrait : {register.filters_label}</p>
        ) : null}
      </header>

      <div className="sticky top-0 z-10 space-y-2 rounded-lg bg-surface p-3 shadow-card">
        <input
          type="search"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Rechercher un article, un donateur"
          aria-label="Rechercher un article, un donateur"
          className="h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text placeholder:text-text-muted"
        />
        <FilterChips label="Catégorie" value={category} onChange={setCategory} options={ARTICLE_CATEGORY_OPTIONS} />
        <div>
          <HolderSearch
            value={holder}
            onChange={setHolder}
            allowUnlocated
            purpose="filter"
            ariaLabel="Détenteur"
            placeholder="Détenteur"
          />
          <p className="mt-1 text-[13px] text-text-muted">Matériel entré chez ce détenteur et encore en sa possession.</p>
        </div>
        <Checkbox checked={includeExits} onChange={setIncludeExits} label="Afficher les sorties" />
      </div>

      {registerQuery.isLoading || holderNotFound ? (
        <div className="space-y-4" aria-busy="true" aria-label="Chargement du registre">
          <div className="h-[3px] w-full animate-pulse rounded bg-primary" />
          <Skeleton variant="card" />
          <Skeleton variant="card" />
          <Skeleton variant="card" />
        </div>
      ) : registerQuery.isError || !register ? (
        <EmptyState
          variant="error"
          message="Impossible de charger le registre."
          actionLabel="Réessayer"
          onAction={() => void registerQuery.refetch()}
        />
      ) : (
        <>
          {register.is_empty ? (
            hasFilter ? (
              <EmptyState
                variant="no-results"
                message={params.search ? `Aucun résultat pour « ${params.search} ».` : "Aucun résultat pour ces filtres."}
                actionLabel="Effacer les filtres"
                onAction={clearFilters}
              />
            ) : (
              <EmptyState message="Le registre est vide." />
            )
          ) : (
            register.sections.map((section) => (
              <SectionCard
                key={`${section.category}-${JSON.stringify(params)}`}
                section={section}
                isWide={isWide}
                onOpenLine={setMovementId}
              />
            ))
          )}

          {register.include_exits ? (
            <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
              <h2 className="mb-3 text-base font-semibold text-text">Sorties de l'année</h2>
              {register.exits.length === 0 ? (
                <p className="text-sm text-text-muted">Aucune sortie cette année.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {register.exits.map((exit) => (
                    <li key={exit.movement_id}>
                      <button
                        type="button"
                        onClick={() => setMovementId(exit.movement_id)}
                        className="block min-h-11 w-full py-2 text-left"
                      >
                        <span className="block text-sm text-text">
                          {exit.movement_type_display} · {exit.designation} ·{" "}
                          <span className="tabular-nums">
                            {exit.quantity} {exit.unit}
                          </span>
                        </span>
                        <span className="block text-[13px] text-text-muted">
                          {formatDateFr(exit.movement_date)} · chez {exit.location}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : null}

          <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
            <h2 className="mb-3 text-base font-semibold text-text">Éléments à déclasser</h2>
            {register.decommissions.length === 0 ? (
              <p className="text-sm text-text-muted">Aucun élément à déclasser.</p>
            ) : (
              <ul className="divide-y divide-border">
                {register.decommissions.map((dec) => (
                  <li key={dec.id}>
                    <button
                      type="button"
                      onClick={() => setDecommissionId(dec.id)}
                      className="block min-h-11 w-full py-2 text-left"
                    >
                      <span className="block text-sm text-text">
                        {dec.designation} :{" "}
                        <span className="tabular-nums">
                          {dec.quantity} {dec.unit}
                        </span>
                      </span>
                      <span className="block text-[13px] text-text-muted">
                        {dec.reason_display}
                        {dec.reason_note ? ` — ${dec.reason_note}` : ""} · chez {dec.location} · signalé le{" "}
                        {formatDateFr(dec.noted_on)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      <MovementDetailModal
        movementId={movementId}
        canSeeExpenseDetail={access.canSeeExpenseDetail}
        onClose={() => setMovementId(null)}
        onOpenDecommission={(id) => {
          setMovementId(null);
          setDecommissionId(id);
        }}
      />

      <DecommissionDetailModal
        decommissionId={decommissionId}
        canManage={access.canManageMaterial}
        onClose={() => setDecommissionId(null)}
        onChanged={(message) => {
          for (const key of ["overview", "articles", "movements", "holders", "decommissions", "register"]) {
            void queryClient.invalidateQueries({ queryKey: ["logistics", key] });
          }
          showToast(message);
        }}
      />
    </div>
  );
}
