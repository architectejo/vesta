import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getMyProfile } from "../../api/clubs";
import { useDeepLink } from "../../hooks/useDeepLink";
import { useClosingState } from "../../hooks/useClosingState";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import {
  createArticle,
  getMaterialOverview,
  listArticles,
  listDecommissions,
  listHolders,
  listMovements,
  openInventory,
  updateArticle,
  type Article,
  type ArticleCategory,
  type ArticleCondition,
  type ArticleInput,
  type MovementType,
  type StockMovement,
  type StockRow,
} from "../../api/logistics";
import {
  Avatar,
  Banner,
  Button,
  Checkbox,
  ConfirmDialog,
  DataTable,
  EmptyState,
  IconButton,
  IconMore,
  IconPin,
  Loader,
  StatusBadge,
  FilterChips,
  useToast,
  type DataTableColumn,
  type FilterChip,
} from "../../design-system";
import { ArticleDetailModal } from "./ArticleDetailModal";
import { ArticleFormModal } from "./ArticleFormModal";
import { CountModal } from "./CountModal";
import { DecommissionDetailModal } from "./DecommissionDetailModal";
import { DecommissionFlagModal } from "./DecommissionFlagModal";
import { DecommissionRows } from "./DecommissionList";
import { DecommissionListModal } from "./DecommissionListModal";
import { formatDateFr } from "./format";
import { HolderDetailModal } from "./HolderDetailModal";
import { HolderFormModal } from "./HolderFormModal";
import { HOLDERS_QUERY_KEY, HolderSearch, UNLOCATED_LABEL, type HolderSelection } from "./HolderSearch";
import { InventoryDetailModal } from "./InventoryDetailModal";
import { getMaterialAccess } from "./materielAccess";
import {
  ALL_MOVEMENT_TYPE_OPTIONS,
  ARTICLE_CATEGORY_OPTIONS,
  ARTICLE_CONDITION_OPTIONS,
  articlesLabel,
  piecesLabel,
} from "./materielLabels";
import { listOutstandingMatchEquipment, type OutstandingEquipmentRow } from "./matchEquipmentAggregate";
import { MatchEquipmentModal } from "./MatchEquipmentModal";
import { MovementDetailModal } from "./MovementDetailModal";
import { RecordMovementModal } from "./RecordMovementModal";
import { TransferModal } from "./TransferModal";
import { UnlocatedModal } from "./UnlocatedModal";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

const OVERVIEW_KEY = ["logistics", "overview"] as const;
const MOVEMENTS_PAGE_SIZE = 50;
const HOLDERS_VISIBLE = 5;

/** Colonne « Chez » du catalogue (spec B4 §1.1) : au-delà de deux détenteurs, « {1er} {qté} · +{k} ». */
export function holderSummary(rows: StockRow[]): ReactNode {
  if (rows.length === 0) return "—";
  const shown = rows.length > 2 ? rows.slice(0, 1) : rows;
  return (
    <span>
      {shown.map((row, index) => (
        <span key={row.holder_id ?? "none"} className={row.holder_id === null ? "text-text-muted" : undefined}>
          {index > 0 ? " · " : ""}
          {row.holder_name} <span className="tabular-nums">{row.quantity}</span>
        </span>
      ))}
      {rows.length > 2 ? <span className="text-text-muted"> · +{rows.length - 1}</span> : null}
    </span>
  );
}

interface TransferState {
  initialFrom?: number | null;
  initialFromName?: string;
}

/** Page « Matériel » (fiche `docs/ecrans/logistique.md`, CDC 4.13 ; spec B4 lots 2 à 4). */
export function MaterielPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const isWide = useMediaQuery("(min-width: 1024px)");

  const [showArchived, setShowArchived] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<ArticleCategory | "">("");
  const [conditionFilter, setConditionFilter] = useState<ArticleCondition | "">("");
  const [catalogueHolder, setCatalogueHolder] = useState<HolderSelection | null>(null);
  const [movementTypeFilter, setMovementTypeFilter] = useState<MovementType | "">("");
  const [movementHolder, setMovementHolder] = useState<HolderSelection | null>(null);
  const [showAllHolders, setShowAllHolders] = useState(false);

  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null);
  const [articleFormOpen, setArticleFormOpen] = useState<"create" | Article | null>(null);
  const [recordMovementOpen, setRecordMovementOpen] = useState(false);
  const [selectedMovementId, setSelectedMovementId] = useState<number | null>(null);
  const [selectedEquipmentMatch, setSelectedEquipmentMatch] = useState<OutstandingEquipmentRow | null>(null);
  const [inventoryDetailId, setInventoryDetailId] = useState<number | null>(null);
  // Lien depuis l'alerte « inventaire non clôturé » (`?inventaire=<id>`).
  useDeepLink("inventaire", setInventoryDetailId);
  const [countModalOpen, setCountModalOpen] = useState(false);
  const [confirmOpenInventory, setConfirmOpenInventory] = useState(false);
  const [openInventoryError, setOpenInventoryError] = useState<string | undefined>(undefined);
  const [openingInventory, setOpeningInventory] = useState(false);

  const [holderDetailId, setHolderDetailId] = useState<number | null>(null);
  const [holderFormOpen, setHolderFormOpen] = useState(false);
  const [unlocatedOpen, setUnlocatedOpen] = useState(false);
  const [transfer, setTransfer] = useState<TransferState | null>(null);
  const [flagOpen, setFlagOpen] = useState(false);
  const [decommissionListOpen, setDecommissionListOpen] = useState(false);
  const [decommissionDetailId, setDecommissionDetailId] = useState<number | null>(null);
  const [headerMenuOpen, setHeaderMenuOpen] = useState(false);
  const headerMenu = useClosingState(headerMenuOpen, 200);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const access = getMaterialAccess(profileQuery.data?.roles);

  // Lien profond depuis « Voir dans le matériel » (détail d'une dépense,
  // fiche `logistique.md` §5.1) : ouvre directement la modale « Mouvement ».
  useEffect(() => {
    const raw = searchParams.get("mouvement");
    if (!raw) return;
    const id = Number(raw);
    if (Number.isFinite(id)) setSelectedMovementId(id);
    const next = new URLSearchParams(searchParams);
    next.delete("mouvement");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const overviewQuery = useQuery({
    queryKey: OVERVIEW_KEY,
    queryFn: getMaterialOverview,
    enabled: access.canReadMaterial,
  });

  const holdersQuery = useQuery({
    queryKey: [...HOLDERS_QUERY_KEY, "list", false],
    queryFn: () => listHolders(false),
    enabled: access.canReadMaterial,
  });

  const articlesQuery = useQuery({
    queryKey: ["logistics", "articles", showArchived, categoryFilter, conditionFilter],
    queryFn: () =>
      listArticles({
        include_archived: showArchived,
        category: categoryFilter || undefined,
        condition: conditionFilter || undefined,
      }),
    enabled: access.canReadMaterial,
  });

  const decommissionsQuery = useQuery({
    queryKey: ["logistics", "decommissions", "list", "all"],
    queryFn: () => listDecommissions(),
    enabled: access.canReadMaterial,
  });

  const outstandingQuery = useQuery({
    queryKey: ["logistics", "outstanding-equipment"],
    queryFn: listOutstandingMatchEquipment,
    enabled: access.canReadMaterial,
  });

  const movementHolderParam: number | "none" | undefined = movementHolder
    ? (movementHolder.id ?? "none")
    : undefined;
  const movementsQuery = useInfiniteQuery({
    queryKey: ["logistics", "movements", "all", movementTypeFilter, movementHolderParam ?? ""],
    queryFn: ({ pageParam }) =>
      listMovements({
        movement_type: movementTypeFilter || undefined,
        holder: movementHolderParam,
        limit: MOVEMENTS_PAGE_SIZE,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.next_offset ?? undefined,
    enabled: access.canReadMaterial,
  });
  const movements = useMemo(
    () => (movementsQuery.data?.pages ?? []).flatMap((page) => page.results),
    [movementsQuery.data],
  );
  const movementsCount = movementsQuery.data?.pages[0]?.count ?? 0;

  function invalidateAll(): void {
    for (const key of ["overview", "articles", "movements", "outstanding-equipment", "holders", "decommissions", "register"]) {
      void queryClient.invalidateQueries({ queryKey: ["logistics", key] });
    }
  }

  function afterWrite(message: string): void {
    invalidateAll();
    showToast(message);
  }

  async function handleArticleFormSubmit(input: ArticleInput): Promise<void> {
    if (articleFormOpen && articleFormOpen !== "create") {
      await updateArticle(articleFormOpen.id, input);
      setArticleFormOpen(null);
      afterWrite("Article modifié.");
    } else {
      await createArticle(input);
      setArticleFormOpen(null);
      invalidateAll();
      showToast("Article ajouté.", {
        actionLabel: "Enregistrer une entrée",
        onAction: () => setRecordMovementOpen(true),
      });
    }
  }

  async function handleOpenInventory(): Promise<void> {
    setOpeningInventory(true);
    setOpenInventoryError(undefined);
    try {
      const inventory = await openInventory();
      setConfirmOpenInventory(false);
      afterWrite(`Inventaire du ${inventory.quarter_label_display} ouvert.`);
    } catch (error) {
      setOpenInventoryError(apiErrorMessage(error));
    } finally {
      setOpeningInventory(false);
    }
  }

  if (profileQuery.isLoading) return <Loader loading variant="page" />;
  if (!access.canReadMaterial) {
    return <EmptyState message="Vous n'avez pas accès à cette page." />;
  }

  const overview = overviewQuery.data;
  const clubName = profileQuery.data?.club.name ?? "";
  const holders = holdersQuery.data;
  const unlocatedTotal = holders?.unlocated.stock_total ?? 0;
  const leftHolders = (holders?.results ?? []).filter((holder) => holder.has_left_club && holder.stock_total > 0);
  const decommissions = decommissionsQuery.data;
  const pendingDecommissions = (decommissions?.results ?? []).filter((d) => d.status === "pending");

  const catalogueRows = (articlesQuery.data?.results ?? []).filter(
    (article) => !catalogueHolder || article.stock_by_holder.some((row) => row.holder_id === catalogueHolder.id),
  );
  const catalogueChips: FilterChip[] = catalogueHolder
    ? [{ label: `Détenteur : ${catalogueHolder.name}`, onRemove: () => setCatalogueHolder(null) }]
    : [];
  const movementChips: FilterChip[] = movementHolder
    ? [{ label: `Détenteur : ${movementHolder.name}`, onRemove: () => setMovementHolder(null) }]
    : [];

  const articleColumns: Array<DataTableColumn<Article>> = [
    {
      key: "article",
      header: "Article",
      widthPx: 180,
      render: (row) => (
        <span>
          <span className="block text-sm text-text">{row.name}</span>
          <span className="block text-[13px] text-text-muted">{row.unit}</span>
        </span>
      ),
    },
    { key: "category", header: "Catégorie", render: (row) => row.category_display },
    {
      key: "in_stock",
      header: "En stock",
      align: "right",
      render: (row) => <span className="tabular-nums">{`${row.in_stock} ${row.unit}`}</span>,
    },
    { key: "holders", header: "Chez", render: (row) => holderSummary(row.stock_by_holder) },
    {
      key: "pending_decommission",
      header: "À déclasser",
      align: "right",
      render: (row) => (row.pending_decommission > 0 ? row.pending_decommission : "—"),
    },
    {
      key: "loaned",
      header: "Sortis (match)",
      align: "right",
      render: (row) => (row.loaned_for_match > 0 ? row.loaned_for_match : "—"),
    },
    { key: "condition", header: "État", render: (row) => row.reference_condition_display },
    {
      key: "status",
      header: "Statut",
      render: (row) => (row.status === "archived" ? <StatusBadge status="archived" /> : null),
    },
  ];

  const movementColumns: Array<DataTableColumn<StockMovement>> = [
    { key: "date", header: "Date", render: (row) => formatDateFr(row.movement_date) },
    { key: "article", header: "Article", widthPx: 160, render: (row) => row.article.name },
    { key: "type", header: "Type", render: (row) => row.movement_type_display },
    {
      key: "quantity",
      header: "Quantité",
      align: "right",
      render: (row) => (
        <span className="tabular-nums">{`${row.signed_quantity > 0 ? "+" : ""}${row.signed_quantity}`}</span>
      ),
    },
    {
      key: "holder",
      header: "Chez",
      render: (row) =>
        row.holder ? row.holder.name : <span className="text-text-muted">{UNLOCATED_LABEL}</span>,
    },
    { key: "player", header: "Joueur", render: (row) => row.membership?.name ?? "—" },
    {
      key: "link",
      header: "Lié à",
      render: (row) =>
        row.match_id ? `Match du ${formatDateFr(row.movement_date)}` : row.expense_id ? "Dépense" : "—",
    },
    { key: "recorded_by", header: "Saisi par", render: (row) => row.recorded_by.name || "Système Vesta" },
  ];

  const cardClass = "rounded-lg bg-surface p-3 shadow-card sm:p-4";

  const inventoryCard = (
    <section key="inventory" className={cardClass}>
      <h2 className="mb-3 text-base font-semibold text-text">Inventaire trimestriel</h2>
      {overviewQuery.isLoading ? (
        <Loader loading variant="list" count={2} />
      ) : overviewQuery.isError ? (
        <EmptyState
          variant="error"
          message="Impossible de charger l'inventaire."
          actionLabel="Réessayer"
          onAction={() => void overviewQuery.refetch()}
        />
      ) : !overview ? null : overview.open_inventory ? (
        <div className="space-y-2">
          <StatusBadge status={overview.blocking_inventory ? "inventory_overdue" : "inventory_open"} />
          <p className="text-sm text-text">
            Ouvert le {formatDateFr(overview.open_inventory.opened_at.slice(0, 10))} par{" "}
            {overview.open_inventory.opened_by.name}
          </p>
          <p className="text-sm text-text-muted">
            {overview.counted} articles comptés sur {overview.total_active_articles}
          </p>
          <button
            type="button"
            className="inline-flex min-h-control-sm items-center text-sm font-medium text-primary-text hover:underline"
            onClick={() => setInventoryDetailId(overview.open_inventory!.id)}
          >
            Voir tout l'inventaire
          </button>
          {access.canManageMaterial ? (
            <div className="flex flex-wrap gap-2 pt-1">
              <Button size="sm" variant="primary" onClick={() => setCountModalOpen(true)}>
                Saisir le comptage
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setInventoryDetailId(overview.open_inventory!.id)}>
                Clôturer l'inventaire
              </Button>
            </div>
          ) : null}
        </div>
      ) : overview.can_open ? (
        <div className="space-y-2">
          {overview.last_closed_inventory ? (
            <p className="text-sm text-text">
              Dernier inventaire : {overview.last_closed_inventory.quarter_label_display}, clôturé le{" "}
              {formatDateFr((overview.last_closed_inventory.closed_at ?? "").slice(0, 10))}.
            </p>
          ) : (
            <EmptyState
              message="Aucun inventaire pour l'instant."
              description="L'inventaire compare le stock compté au stock enregistré, une fois par trimestre."
            />
          )}
          {access.canManageMaterial ? (
            <Button size="sm" variant="primary" onClick={() => setConfirmOpenInventory(true)}>
              Ouvrir l'inventaire du {overview.openable_quarter_label_display}
            </Button>
          ) : null}
        </div>
      ) : null}
    </section>
  );

  const visibleHolders = showAllHolders ? (holders?.results ?? []) : (holders?.results ?? []).slice(0, HOLDERS_VISIBLE);
  const holdersCard = (
    <section key="holders" className={cardClass}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-text">
          Où est le matériel{" "}
          {holders ? <span className="text-text-muted">· {holders.count} détenteurs</span> : null}
        </h2>
        {access.canManageMaterial && (holders?.count ?? 0) > 0 ? (
          <Button size="sm" variant="secondary" onClick={() => setHolderFormOpen(true)}>
            Ajouter un détenteur
          </Button>
        ) : null}
      </div>
      {holdersQuery.isLoading ? (
        <Loader loading variant="list" count={3} />
      ) : holdersQuery.isError ? (
        <EmptyState
          variant="error"
          message="Impossible de charger les détenteurs."
          actionLabel="Réessayer"
          onAction={() => void holdersQuery.refetch()}
        />
      ) : !holders || holders.count === 0 ? (
        <EmptyState
          message="Aucun détenteur enregistré."
          description="Indiquez chez qui se trouve le matériel pour le retrouver et le compter plus vite."
          actionLabel={access.canManageMaterial ? "Ajouter un détenteur" : undefined}
          onAction={access.canManageMaterial ? () => setHolderFormOpen(true) : undefined}
        />
      ) : (
        <>
          <ul className="divide-y divide-border">
            {visibleHolders.map((holder) => (
              <li key={holder.id}>
                <button
                  type="button"
                  onClick={() => setHolderDetailId(holder.id)}
                  className="flex min-h-11 w-full items-center justify-between gap-2 py-2 text-left"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    {holder.kind === "member" ? (
                      <Avatar name={holder.name} size={24} />
                    ) : (
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-muted text-text-muted">
                        <IconPin aria-hidden="true" className="h-3.5 w-3.5" />
                      </span>
                    )}
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-text">{holder.name}</span>
                      <span className="flex items-center gap-2 text-[13px] text-text-muted">
                        {articlesLabel(holder.articles_count)}
                        {holder.has_left_club ? <StatusBadge status="holder_left" /> : null}
                      </span>
                    </span>
                  </span>
                  <span className="shrink-0 tabular-nums text-sm text-text">{piecesLabel(holder.stock_total)}</span>
                </button>
              </li>
            ))}
            {unlocatedTotal > 0 ? (
              <li>
                <button
                  type="button"
                  onClick={() => setUnlocatedOpen(true)}
                  className="flex min-h-11 w-full items-center justify-between gap-2 py-2 text-left"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <span
                      aria-hidden="true"
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-muted text-sm text-text-muted"
                    >
                      ?
                    </span>
                    <span className="text-sm text-text-muted">{UNLOCATED_LABEL}</span>
                    <StatusBadge status="unlocated" />
                  </span>
                  <span className="shrink-0 tabular-nums text-sm text-text">{piecesLabel(unlocatedTotal)}</span>
                </button>
              </li>
            ) : null}
          </ul>
          {holders.results.length > HOLDERS_VISIBLE && !showAllHolders ? (
            <div className="mt-2 text-center">
              <Button size="sm" variant="secondary" onClick={() => setShowAllHolders(true)}>
                Voir plus
              </Button>
            </div>
          ) : null}
        </>
      )}
    </section>
  );

  const catalogueCard = (
    <section key="catalogue" className={cardClass}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-text">
          Catalogue <span className="text-text-muted">· {articlesQuery.data?.count ?? 0} articles</span>
        </h2>
        {access.canManageMaterial ? (
          <Button size="sm" variant="secondary" onClick={() => setArticleFormOpen("create")}>
            Ajouter un article
          </Button>
        ) : null}
      </div>
      <DataTable
        columns={articleColumns}
        rows={catalogueRows}
        getRowId={(row) => row.id}
        loading={articlesQuery.isLoading}
        onRowClick={(row) => setSelectedArticle(row)}
        getSearchableText={(row) => row.name}
        searchPlaceholder="Rechercher un article"
        resultLabel="articles"
        activeFilterChips={catalogueChips}
        filtersSlot={
          <div className="w-full space-y-2">
            <FilterChips
              label="Catégorie"
              value={categoryFilter}
              onChange={setCategoryFilter}
              options={ARTICLE_CATEGORY_OPTIONS}
            />
            <FilterChips
              label="État"
              value={conditionFilter}
              onChange={setConditionFilter}
              options={ARTICLE_CONDITION_OPTIONS}
              allLabel="Tous"
            />
            <div className="flex flex-wrap items-center gap-2">
              <div className="w-full sm:w-64">
                <HolderSearch
                  value={catalogueHolder}
                  onChange={setCatalogueHolder}
                  allowUnlocated
                  purpose="filter"
                  ariaLabel="Filtrer par détenteur"
                  placeholder="Détenteur"
                />
              </div>
              <Checkbox checked={showArchived} onChange={setShowArchived} label="Afficher les articles archivés" />
            </div>
          </div>
        }
        emptyState={
          <EmptyState
            message="Aucun article dans le catalogue."
            actionLabel={access.canManageMaterial ? "Ajouter un article" : undefined}
            onAction={access.canManageMaterial ? () => setArticleFormOpen("create") : undefined}
          />
        }
      />
    </section>
  );

  // Carte masquée sans aucun signalement (écart n° 8 de la spec B4, à valider).
  const decommissionCard =
    (decommissions?.count ?? 0) > 0 || decommissionsQuery.isLoading || decommissionsQuery.isError ? (
      <section key="decommissions" className={cardClass}>
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-text">
            À déclasser{" "}
            {decommissions ? (
              <span className="block text-[13px] font-normal text-text-muted">
                {piecesLabel(decommissions.pending_quantity)} en attente de sortie
              </span>
            ) : null}
          </h2>
          {access.canManageMaterial ? (
            <Button size="sm" variant="secondary" onClick={() => setFlagOpen(true)}>
              Signaler à déclasser
            </Button>
          ) : null}
        </div>
        {decommissionsQuery.isLoading ? (
          <Loader loading variant="list" count={2} />
        ) : decommissionsQuery.isError ? (
          <EmptyState
            variant="error"
            message="Impossible de charger cette section."
            actionLabel="Réessayer"
            onAction={() => void decommissionsQuery.refetch()}
          />
        ) : pendingDecommissions.length === 0 ? (
          <EmptyState message="Aucun élément à déclasser." />
        ) : (
          <DecommissionRows rows={pendingDecommissions.slice(0, 5)} onOpen={setDecommissionDetailId} />
        )}
        {(decommissions?.count ?? 0) > 0 ? (
          <div className="mt-2 text-center">
            <Button size="sm" variant="secondary" onClick={() => setDecommissionListOpen(true)}>
              Voir plus
            </Button>
          </div>
        ) : null}
      </section>
    ) : null;

  const outstandingCard = (
    <section key="outstanding" className={cardClass}>
      <h2 className="mb-3 text-base font-semibold text-text">Sortis pour un match</h2>
      {outstandingQuery.isLoading ? (
        <Loader loading variant="list" count={2} />
      ) : outstandingQuery.isError ? (
        <EmptyState
          variant="error"
          message="Impossible de charger cette section."
          actionLabel="Réessayer"
          onAction={() => void outstandingQuery.refetch()}
        />
      ) : (outstandingQuery.data?.length ?? 0) === 0 ? (
        <EmptyState message="Aucun équipement sorti pour un match." />
      ) : (
        <ul className="divide-y divide-border">
          {outstandingQuery.data!.slice(0, 5).map((row) => (
            <li key={`${row.matchId}-${row.articleId}`}>
              <button
                type="button"
                onClick={() => setSelectedEquipmentMatch(row)}
                className="flex w-full flex-col gap-0.5 py-2 text-left"
              >
                <span className="text-sm text-text">
                  {row.opponent} · {formatDateFr(row.eventDate)}
                </span>
                <span className="flex items-center gap-2 text-xs text-text-muted">
                  {row.articleName} · {row.outQuantity} sortis · {row.returnedQuantity} rendus
                  <StatusBadge status={row.status === "out" ? "equipment_out" : "equipment_partially_returned"} />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );

  const movementsCard = (
    <section key="movements" className={cardClass}>
      <h2 className="mb-3 text-base font-semibold text-text">
        Registre des mouvements{" "}
        {movementsQuery.data ? <span className="text-text-muted">· {movementsCount} mouvements</span> : null}
      </h2>
      {movementsQuery.isError ? (
        <EmptyState
          variant="error"
          message="Impossible de charger les mouvements."
          actionLabel="Réessayer"
          onAction={() => void movementsQuery.refetch()}
        />
      ) : (
        <DataTable
        columns={movementColumns}
        rows={movements}
        getRowId={(row) => row.id}
        loading={movementsQuery.isLoading}
        onRowClick={(row) => setSelectedMovementId(row.id)}
        getSearchableText={(row) => `${row.article.name} ${row.membership?.name ?? ""} ${row.holder?.name ?? ""}`}
        searchPlaceholder="Rechercher dans les mouvements affichés"
        resultLabel="mouvements affichés"
        pageSize={100_000}
        activeFilterChips={movementChips}
        filtersSlot={
          <div className="flex w-full flex-wrap items-center gap-2">
            <select
              value={movementTypeFilter}
              onChange={(e) => setMovementTypeFilter(e.target.value as MovementType | "")}
              className="h-control-sm rounded-sm border border-border-strong bg-surface px-2 text-sm text-text"
              aria-label="Type"
            >
              <option value="">Tous les types</option>
              {ALL_MOVEMENT_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <div className="w-full sm:w-64">
              <HolderSearch
                value={movementHolder}
                onChange={setMovementHolder}
                allowUnlocated
                purpose="filter"
                ariaLabel="Filtrer les mouvements par détenteur"
                placeholder="Détenteur"
              />
            </div>
          </div>
        }
        emptyState={
          <EmptyState
            message="Aucun mouvement enregistré."
            actionLabel={access.canManageMaterial ? "Enregistrer un mouvement" : undefined}
            onAction={access.canManageMaterial ? () => setRecordMovementOpen(true) : undefined}
          />
        }
      />
      )}
      {!movementsQuery.isError && movementsQuery.hasNextPage ? (
        <div className="mt-2 text-center">
          <Button
            size="sm"
            variant="secondary"
            loading={movementsQuery.isFetchingNextPage}
            loadingLabel="Chargement…"
            onClick={() => void movementsQuery.fetchNextPage()}
          >
            Voir plus
          </Button>
        </div>
      ) : null}
    </section>
  );

  const pastInventoriesCard = (
    <section key="past" className={cardClass}>
      <h2 className="mb-3 text-base font-semibold text-text">Inventaires passés</h2>
      {!overview?.last_closed_inventory ? (
        <EmptyState message="Aucun inventaire clôturé." />
      ) : (
        <ul className="divide-y divide-border">
          <li>
            <button
              type="button"
              className="flex w-full items-center justify-between gap-2 py-2 text-left"
              onClick={() => setInventoryDetailId(overview.last_closed_inventory!.id)}
            >
              <span className="min-w-0">
                <span className="block text-sm text-text">{overview.last_closed_inventory.quarter_label_display}</span>
                <span className="block text-xs text-text-muted">
                  Clôturé le {formatDateFr((overview.last_closed_inventory.closed_at ?? "").slice(0, 10))} par{" "}
                  {overview.last_closed_inventory.closed_by?.name ?? ""}
                </span>
              </span>
              <StatusBadge status="inventory_closed" />
            </button>
          </li>
        </ul>
      )}
    </section>
  );

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">Matériel</h1>
          <p className="text-sm text-text-muted">
            {clubName}
            {overview ? ` · ${overview.current_quarter_label_display}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => navigate("/materiel/registre")}>
            Registre de l'intendance
          </Button>
          {access.canManageMaterial ? (
            <>
              <Button variant="secondary" size="sm" onClick={() => setArticleFormOpen("create")}>
                Ajouter un article
              </Button>
              <Button variant="primary" size="sm" onClick={() => setRecordMovementOpen(true)}>
                Enregistrer un mouvement
              </Button>
              <div className="relative">
                <IconButton
                  aria-label="Plus d'actions"
                  onClick={() => setHeaderMenuOpen((v) => !v)}
                  icon={<IconMore aria-hidden="true" className="h-5 w-5" />}
                />
                {headerMenu.mounted ? (
                  <div
                    data-state={headerMenu.dataState}
                    onAnimationEnd={headerMenu.onAnimationEnd}
                    className="vesta-anim-menu absolute right-0 z-10 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated"
                  >
                    <button
                      type="button"
                      className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                      onClick={() => {
                        setHeaderMenuOpen(false);
                        setFlagOpen(true);
                      }}
                    >
                      Signaler à déclasser
                    </button>
                  </div>
                ) : null}
              </div>
            </>
          ) : null}
        </div>
      </header>

      {overview?.blocking_inventory && overview.open_inventory ? (
        <Banner
          variant="danger"
          action={
            <Button size="sm" variant="secondary" onClick={() => setInventoryDetailId(overview.open_inventory!.id)}>
              {access.canManageMaterial ? "Reprendre l'inventaire" : "Voir l'inventaire"}
            </Button>
          }
        >
          <span>
            L'inventaire du {overview.open_inventory.quarter_label_display} n'est pas clôturé : l'inventaire suivant ne
            peut pas être ouvert.
            <br />
            <span className="text-[13px]">
              Reste à faire : {overview.to_count} article(s) à compter, {overview.to_justify} écart(s) à justifier.
            </span>
          </span>
        </Banner>
      ) : null}

      {access.canManageMaterial && (holders?.count ?? 0) >= 1 && unlocatedTotal > 0 ? (
        <Banner
          variant="info"
          action={
            <Button size="sm" variant="secondary" onClick={() => setTransfer({ initialFrom: null })}>
              Localiser
            </Button>
          }
        >
          {unlocatedTotal} pièce(s) ne sont rattachées à aucun détenteur.
        </Banner>
      ) : null}

      {access.canSeeLeftHolderAlert
        ? leftHolders.map((holder) => (
            <Banner
              key={holder.id}
              variant="warning"
              action={
                access.canManageMaterial ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setTransfer({ initialFrom: holder.id, initialFromName: holder.name })}
                  >
                    Déplacer
                  </Button>
                ) : undefined
              }
            >
              {holder.name} a quitté le club et détient encore {holder.stock_total} pièce(s).
            </Banner>
          ))
        : null}

      {isWide ? (
        <div className="grid grid-cols-3 items-start gap-4">
          <div className="col-span-1 space-y-4">
            {inventoryCard}
            {holdersCard}
            {decommissionCard}
            {outstandingCard}
            {pastInventoriesCard}
          </div>
          <div className="col-span-2 space-y-4">
            {catalogueCard}
            {movementsCard}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {inventoryCard}
          {holdersCard}
          {catalogueCard}
          {decommissionCard}
          {outstandingCard}
          {movementsCard}
          {pastInventoriesCard}
        </div>
      )}

      <ArticleFormModal
        open={articleFormOpen !== null}
        article={articleFormOpen && articleFormOpen !== "create" ? articleFormOpen : null}
        onClose={() => setArticleFormOpen(null)}
        onSubmit={handleArticleFormSubmit}
      />

      <ArticleDetailModal
        article={selectedArticle}
        canManage={access.canManageMaterial}
        canSeeExpenseDetail={access.canSeeExpenseDetail}
        onClose={() => setSelectedArticle(null)}
        onEdit={(article) => {
          setSelectedArticle(null);
          setArticleFormOpen(article);
        }}
        onChanged={afterWrite}
        onOpenMatch={(matchId) => navigate(`/matchs/${matchId}`)}
        onOpenExpense={(expenseId) => navigate(`/tresorerie/depenses?depense=${expenseId}`)}
      />

      <RecordMovementModal
        open={recordMovementOpen}
        onClose={() => setRecordMovementOpen(false)}
        onSaved={(message) => {
          setRecordMovementOpen(false);
          afterWrite(message);
        }}
      />

      <MovementDetailModal
        movementId={selectedMovementId}
        canSeeExpenseDetail={access.canSeeExpenseDetail}
        onClose={() => setSelectedMovementId(null)}
        onOpenMatch={(matchId) => navigate(`/matchs/${matchId}`)}
        onOpenExpense={(expenseId) => navigate(`/tresorerie/depenses?depense=${expenseId}`)}
        onOpenDecommission={(id) => {
          setSelectedMovementId(null);
          setDecommissionDetailId(id);
        }}
      />

      <HolderDetailModal
        holderId={holderDetailId}
        canManage={access.canManageMaterial}
        canSeeExpenseDetail={access.canSeeExpenseDetail}
        onClose={() => setHolderDetailId(null)}
        onChanged={afterWrite}
        onShowAllMovements={(holder) => {
          setHolderDetailId(null);
          setMovementHolder({ id: holder.id, name: holder.name });
        }}
      />

      <HolderFormModal
        open={holderFormOpen}
        onClose={() => setHolderFormOpen(false)}
        onCreated={() => {
          setHolderFormOpen(false);
          invalidateAll();
        }}
      />

      <UnlocatedModal
        open={unlocatedOpen}
        canManage={access.canManageMaterial}
        onClose={() => setUnlocatedOpen(false)}
        onLocate={() => {
          setUnlocatedOpen(false);
          setTransfer({ initialFrom: null });
        }}
      />

      <TransferModal
        open={transfer !== null}
        initialFrom={transfer?.initialFrom}
        initialFromName={transfer?.initialFromName}
        onClose={() => setTransfer(null)}
        onSaved={(message) => {
          setTransfer(null);
          afterWrite(message);
        }}
      />

      <DecommissionFlagModal
        open={flagOpen}
        onClose={() => setFlagOpen(false)}
        onSaved={(message) => {
          setFlagOpen(false);
          afterWrite(message);
        }}
      />

      <DecommissionListModal
        open={decommissionListOpen}
        onClose={() => setDecommissionListOpen(false)}
        onOpenDecommission={(id) => {
          setDecommissionListOpen(false);
          setDecommissionDetailId(id);
        }}
      />

      <DecommissionDetailModal
        decommissionId={decommissionDetailId}
        canManage={access.canManageMaterial}
        onClose={() => setDecommissionDetailId(null)}
        onChanged={afterWrite}
      />

      {selectedEquipmentMatch ? (
        <MatchEquipmentModal
          open
          matchId={selectedEquipmentMatch.matchId}
          opponent={selectedEquipmentMatch.opponent}
          eventDate={selectedEquipmentMatch.eventDate}
          canRecordReturn={access.canManageMaterial || access.isCoach}
          onClose={() => setSelectedEquipmentMatch(null)}
          onReturned={() => afterWrite("Retour enregistré.")}
        />
      ) : null}

      <InventoryDetailModal
        inventoryId={inventoryDetailId}
        canManage={access.canManageMaterial}
        onClose={() => setInventoryDetailId(null)}
        onOpenCount={() => setCountModalOpen(true)}
        onClosed={(message) => {
          setInventoryDetailId(null);
          afterWrite(message);
        }}
      />

      {overview?.open_inventory ? (
        <CountModal
          open={countModalOpen}
          inventoryId={overview.open_inventory.id}
          quarterLabelDisplay={overview.open_inventory.quarter_label_display}
          onClose={() => setCountModalOpen(false)}
          onSaved={(message) => {
            setCountModalOpen(false);
            setInventoryDetailId(overview.open_inventory!.id);
            afterWrite(message);
          }}
        />
      ) : null}

      <ConfirmDialog
        open={confirmOpenInventory}
        title={`Ouvrir l'inventaire du ${overview?.openable_quarter_label_display ?? ""} ?`}
        description={
          <span>
            Vous saisirez ensuite le stock compté de chaque article. Le stock théorique de chaque article est figé au
            moment de son comptage.
          </span>
        }
        error={openInventoryError}
        confirmLabel="Ouvrir l'inventaire"
        danger={false}
        loading={openingInventory}
        onConfirm={() => void handleOpenInventory()}
        onCancel={() => setConfirmOpenInventory(false)}
      />
    </div>
  );
}
