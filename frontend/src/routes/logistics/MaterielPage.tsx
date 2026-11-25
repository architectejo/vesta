import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getMyProfile } from "../../api/clubs";
import { useDeepLink } from "../../hooks/useDeepLink";
import {
  createArticle,
  getMaterialOverview,
  listArticles,
  listMovements,
  openInventory,
  updateArticle,
  type Article,
  type ArticleCategory,
  type ArticleCondition,
  type ArticleInput,
  type MovementType,
  type StockMovement,
} from "../../api/logistics";
import {
  Banner,
  Button,
  Checkbox,
  ConfirmDialog,
  DataTable,
  EmptyState,
  Loader,
  StatusBadge,
  useToast,
  type DataTableColumn,
} from "../../design-system";
import { ArticleDetailModal } from "./ArticleDetailModal";
import { ArticleFormModal } from "./ArticleFormModal";
import { CountModal } from "./CountModal";
import { formatDateFr } from "./format";
import { InventoryDetailModal } from "./InventoryDetailModal";
import { getMaterialAccess } from "./materielAccess";
import { ARTICLE_CATEGORY_OPTIONS, ARTICLE_CONDITION_OPTIONS } from "./materielLabels";
import { listOutstandingMatchEquipment, type OutstandingEquipmentRow } from "./matchEquipmentAggregate";
import { MatchEquipmentModal } from "./MatchEquipmentModal";
import { MovementDetailModal } from "./MovementDetailModal";
import { RecordMovementModal } from "./RecordMovementModal";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

const OVERVIEW_KEY = ["logistics", "overview"] as const;

/** Page « Matériel » (fiche `docs/ecrans/logistique.md`, CDC 4.13). */
export function MaterielPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [showArchived, setShowArchived] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<ArticleCategory | "">("");
  const [conditionFilter, setConditionFilter] = useState<ArticleCondition | "">("");
  const [movementTypeFilter, setMovementTypeFilter] = useState<MovementType | "">("");

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

  const outstandingQuery = useQuery({
    queryKey: ["logistics", "outstanding-equipment"],
    queryFn: listOutstandingMatchEquipment,
    enabled: access.canReadMaterial,
  });

  const movementsQuery = useQuery({
    queryKey: ["logistics", "movements", "all", movementTypeFilter],
    queryFn: () => listMovements({ movement_type: movementTypeFilter || undefined }),
    enabled: access.canReadMaterial,
  });

  function invalidateAll(): void {
    void queryClient.invalidateQueries({ queryKey: OVERVIEW_KEY });
    void queryClient.invalidateQueries({ queryKey: ["logistics", "articles"] });
    void queryClient.invalidateQueries({ queryKey: ["logistics", "movements"] });
    void queryClient.invalidateQueries({ queryKey: ["logistics", "outstanding-equipment"] });
  }

  async function handleArticleFormSubmit(input: ArticleInput): Promise<void> {
    if (articleFormOpen && articleFormOpen !== "create") {
      await updateArticle(articleFormOpen.id, input);
      setArticleFormOpen(null);
      invalidateAll();
      showToast("Article modifié.");
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
      invalidateAll();
      showToast(`Inventaire du ${inventory.quarter_label_display} ouvert.`);
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
      render: (row) => `${row.in_stock} ${row.unit}`,
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
      render: (row) => `${row.signed_quantity > 0 ? "+" : ""}${row.signed_quantity}`,
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
        {access.canManageMaterial ? (
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => setArticleFormOpen("create")}>
              Ajouter un article
            </Button>
            <Button variant="primary" size="sm" onClick={() => setRecordMovementOpen(true)}>
              Enregistrer un mouvement
            </Button>
          </div>
        ) : null}
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
            L'inventaire du {overview.open_inventory.quarter_label_display} n'est pas clôturé : l'inventaire suivant
            ne peut pas être ouvert.
            <br />
            <span className="text-[13px]">
              Reste à faire : {overview.to_count} article(s) à compter, {overview.to_justify} écart(s) à justifier.
            </span>
          </span>
        </Banner>
      ) : null}

      {/* Inventaire trimestriel */}
      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
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
              className="text-sm font-medium text-primary-text hover:underline"
              onClick={() => setInventoryDetailId(overview.open_inventory!.id)}
            >
              Voir tout l'inventaire
            </button>
            {access.canManageMaterial ? (
              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="sm" variant="primary" onClick={() => setCountModalOpen(true)}>
                  Saisir le comptage
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setInventoryDetailId(overview.open_inventory!.id)}
                >
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

      {/* Catalogue */}
      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
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
          rows={articlesQuery.data?.results ?? []}
          getRowId={(row) => row.id}
          loading={articlesQuery.isLoading}
          onRowClick={(row) => setSelectedArticle(row)}
          getSearchableText={(row) => row.name}
          searchPlaceholder="Rechercher un article"
          resultLabel="articles"
          filtersSlot={
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value as ArticleCategory | "")}
                className="h-control-sm rounded-sm border border-border-strong bg-surface px-2 text-sm text-text"
                aria-label="Catégorie"
              >
                <option value="">Toutes catégories</option>
                {ARTICLE_CATEGORY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select
                value={conditionFilter}
                onChange={(e) => setConditionFilter(e.target.value as ArticleCondition | "")}
                className="h-control-sm rounded-sm border border-border-strong bg-surface px-2 text-sm text-text"
                aria-label="État"
              >
                <option value="">Tous états</option>
                {ARTICLE_CONDITION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <Checkbox checked={showArchived} onChange={setShowArchived} label="Afficher les articles archivés" />
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

      {/* Sortis pour un match */}
      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
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

      {/* Registre des mouvements */}
      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <h2 className="mb-3 text-base font-semibold text-text">Registre des mouvements</h2>
        <DataTable
          columns={movementColumns}
          rows={movementsQuery.data?.results ?? []}
          getRowId={(row) => row.id}
          loading={movementsQuery.isLoading}
          onRowClick={(row) => setSelectedMovementId(row.id)}
          getSearchableText={(row) => `${row.article.name} ${row.membership?.name ?? ""}`}
          searchPlaceholder="Rechercher un article ou un joueur"
          resultLabel="mouvements"
          filtersSlot={
            <select
              value={movementTypeFilter}
              onChange={(e) => setMovementTypeFilter(e.target.value as MovementType | "")}
              className="h-control-sm rounded-sm border border-border-strong bg-surface px-2 text-sm text-text"
              aria-label="Type"
            >
              <option value="">Tous les types</option>
              <option value="in_purchase">Achat</option>
              <option value="in_donation">Dotation</option>
              <option value="in_return">Retour</option>
              <option value="out_distribution">Distribution</option>
              <option value="out_loan">Prêt pour un match</option>
              <option value="out_wear">Usure</option>
              <option value="out_loss">Perte</option>
            </select>
          }
          emptyState={
            <EmptyState
              message="Aucun mouvement enregistré."
              actionLabel={access.canManageMaterial ? "Enregistrer un mouvement" : undefined}
              onAction={access.canManageMaterial ? () => setRecordMovementOpen(true) : undefined}
            />
          }
        />
      </section>

      {/* Inventaires passés */}
      <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
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
                  <span className="block text-sm text-text">
                    {overview.last_closed_inventory.quarter_label_display}
                  </span>
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
        onChanged={(message) => {
          invalidateAll();
          showToast(message);
        }}
        onOpenMatch={(matchId) => navigate(`/matchs/${matchId}`)}
        onOpenExpense={(expenseId) => navigate(`/tresorerie/depenses?depense=${expenseId}`)}
      />

      <RecordMovementModal
        open={recordMovementOpen}
        onClose={() => setRecordMovementOpen(false)}
        onSaved={(message) => {
          setRecordMovementOpen(false);
          invalidateAll();
          showToast(message);
        }}
      />

      <MovementDetailModal
        movementId={selectedMovementId}
        canSeeExpenseDetail={access.canSeeExpenseDetail}
        onClose={() => setSelectedMovementId(null)}
        onOpenMatch={(matchId) => navigate(`/matchs/${matchId}`)}
        onOpenExpense={(expenseId) => navigate(`/tresorerie/depenses?depense=${expenseId}`)}
      />

      {selectedEquipmentMatch ? (
        <MatchEquipmentModal
          open
          matchId={selectedEquipmentMatch.matchId}
          opponent={selectedEquipmentMatch.opponent}
          eventDate={selectedEquipmentMatch.eventDate}
          canRecordReturn={access.canManageMaterial || access.isCoach}
          onClose={() => setSelectedEquipmentMatch(null)}
          onReturned={() => {
            invalidateAll();
            showToast("Retour enregistré.");
          }}
        />
      ) : null}

      <InventoryDetailModal
        inventoryId={inventoryDetailId}
        canManage={access.canManageMaterial}
        onClose={() => setInventoryDetailId(null)}
        onOpenCount={() => setCountModalOpen(true)}
        onClosed={(message) => {
          setInventoryDetailId(null);
          invalidateAll();
          showToast(message);
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
            invalidateAll();
            showToast(message);
          }}
        />
      ) : null}

      <ConfirmDialog
        open={confirmOpenInventory}
        title={`Ouvrir l'inventaire du ${overview?.openable_quarter_label_display ?? ""} ?`}
        description={
          <>
            <span>
              Vous saisirez ensuite le stock compté de chaque article. Le stock théorique de chaque article est figé
              au moment de son comptage.
            </span>
            {openInventoryError ? <span className="mt-2 block text-status-danger-fg">{openInventoryError}</span> : null}
          </>
        }
        confirmLabel="Ouvrir l'inventaire"
        danger={false}
        loading={openingInventory}
        onConfirm={() => void handleOpenInventory()}
        onCancel={() => setConfirmOpenInventory(false)}
      />
    </div>
  );
}
