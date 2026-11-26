import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { getMyProfile } from "../../api/clubs";
import {
  archiveExpenseCategory,
  createExpense,
  createExpenseCategory,
  getExpenseCategories,
  getExpenseSummary,
  getExpenses,
  getTreasuryCapabilities,
  updateExpenseCategory,
  type Expense,
  type ExpenseCategory,
  type ExpenseCategoryInput,
  type ExpenseStatus,
} from "../../api/treasury";
import {
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
  Loader,
  StatusBadge,
  useToast,
  type DataTableColumn,
} from "../../design-system";
import { CreateExpenseModal, type CreateExpenseFormValues } from "./CreateExpenseModal";
import { ExpenseCategoryDetailModal } from "./ExpenseCategoryDetailModal";
import { ExpenseCategoryModal } from "./ExpenseCategoryModal";
import { ExpenseDetailModal } from "./ExpenseDetailModal";
import { describeExpenseCategory, expenseStatusKey } from "./expenseLabels";
import { formatAmount, formatDateFr } from "./money";
import { KebabMenu } from "./KebabMenu";

const CAPABILITIES_QUERY_KEY = ["treasury", "capabilities"] as const;
const SUMMARY_QUERY_KEY = ["treasury", "expense-summary"] as const;
const CATEGORIES_QUERY_KEY = ["treasury", "expense-categories", "active"] as const;
const PENDING_STATUSES: ExpenseStatus[] = ["pending"];
const RECENT_STATUSES: ExpenseStatus[] = ["released", "justified", "unjustified", "refused"];
const PAGE_STEP = 20;
const EXPANDED_THRESHOLD = 30;

function apiErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.detail : fallback;
}

interface ExpenseRowProps {
  expense: Expense;
  showStatus: boolean;
  onOpen: (id: number) => void;
}

function ExpenseRow({ expense, showStatus, onOpen }: ExpenseRowProps) {
  return (
    <button
      type="button"
      onClick={() => onOpen(expense.id)}
      className="flex w-full flex-wrap items-center justify-between gap-2 py-3 text-left first:pt-0 last:pb-0"
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-text">{expense.category.name}</span>
        <span className="block truncate text-xs text-text-muted">
          {expense.beneficiary_name} · {formatDateFr(expense.expense_date)}
          {!showStatus ? ` · ${expense.created_by.name ?? ""}` : ""}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-2">
        <span className="tabular-nums text-sm text-text">{formatAmount(expense.amount, expense.currency)}</span>
        <StatusBadge status={expenseStatusKey(expense.status)} />
      </span>
    </button>
  );
}

interface CategoryRowProps {
  category: ExpenseCategory;
  currency: string;
  onOpen: (category: ExpenseCategory) => void;
}

function CategoryRow({ category, currency, onOpen }: CategoryRowProps) {
  return (
    <button
      type="button"
      onClick={() => onOpen(category)}
      className="flex w-full items-center justify-between gap-2 py-3 text-left first:pt-0 last:pb-0"
    >
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium text-text">{category.name}</span>
        <span className="block truncate text-xs text-text-muted">{describeExpenseCategory(category, currency)}</span>
      </span>
    </button>
  );
}

interface AllExpensesTableProps {
  onOpen: (id: number) => void;
}

const STATUS_FILTER_OPTIONS: Array<{ value: ExpenseStatus; label: string }> = [
  { value: "pending", label: "En attente" },
  { value: "released", label: "Libérée" },
  { value: "justified", label: "Justifiée" },
  { value: "unjustified", label: "Non justifiée" },
  { value: "refused", label: "Refusée" },
];

/** Vue élargie au-delà de 30 dépenses (§3.1) : `DataTable` paginée, recherche
 * et filtres. Récupère l'ensemble des dépenses en une fois, comme la grille
 * des cotisations (simplification signalée en compte rendu). */
function AllExpensesTable({ onOpen }: AllExpensesTableProps) {
  const [statusFilter, setStatusFilter] = useState<ExpenseStatus | "">("");
  const allQuery = useQuery({
    queryKey: ["treasury", "expenses", "all"],
    queryFn: () => getExpenses({ limit: 500 }),
  });
  const rows = useMemo(() => {
    const items = allQuery.data?.results ?? [];
    return statusFilter ? items.filter((item) => item.status === statusFilter) : items;
  }, [allQuery.data, statusFilter]);

  const columns: Array<DataTableColumn<Expense>> = [
    { key: "date", header: "Date", render: (row) => formatDateFr(row.expense_date) },
    { key: "category", header: "Catégorie", render: (row) => row.category.name },
    { key: "beneficiary", header: "Bénéficiaire", render: (row) => row.beneficiary_name },
    {
      key: "amount",
      header: "Montant",
      align: "right",
      render: (row) => formatAmount(row.amount, row.currency),
    },
    { key: "created_by", header: "Saisie par", render: (row) => row.created_by.name ?? "—" },
    { key: "status", header: "Statut", render: (row) => <StatusBadge status={expenseStatusKey(row.status)} /> },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows}
      getRowId={(row) => row.id}
      loading={allQuery.isLoading}
      onRowClick={(row) => onOpen(row.id)}
      getSearchableText={(row) => `${row.category.name} ${row.beneficiary_name} ${row.reason}`}
      searchPlaceholder="Rechercher une dépense"
      resultLabel="dépenses"
      filtersSlot={
        <label className="text-sm text-text">
          <span className="sr-only">Statut</span>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as ExpenseStatus | "")}
            className="h-control-sm rounded-sm border border-border-strong bg-surface px-2 text-sm text-text"
          >
            <option value="">Tous les statuts</option>
            {STATUS_FILTER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      }
      emptyState={<EmptyState message="Aucune dépense ne correspond à ces filtres." />}
    />
  );
}

/**
 * Écran « Dépenses » (fiche `docs/ecrans/tresorerie-depenses-assistance.md`
 * §3 ; CDC 4.5.1, 4.5.2). Réservé au Président, Vice-président, Trésorier et
 * Trésorier adjoint (`can_read_expenses`) ; les actions de saisie, de
 * validation et de gestion des catégories dépendent des capacités
 * correspondantes, jamais d'une matrice recopiée dans l'interface.
 */
export function DepensesPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [pendingLimit, setPendingLimit] = useState(PAGE_STEP);
  const [recentLimit, setRecentLimit] = useState(PAGE_STEP);
  const [expandedView, setExpandedView] = useState(false);
  const [detailExpenseId, setDetailExpenseId] = useState<number | null>(null);
  const [showCreateExpense, setShowCreateExpense] = useState(false);
  const [showCategoryForm, setShowCategoryForm] = useState(false);
  const [editingCategory, setEditingCategory] = useState<ExpenseCategory | undefined>(undefined);
  const [detailCategory, setDetailCategory] = useState<ExpenseCategory | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<ExpenseCategory | null>(null);
  const [createError, setCreateError] = useState<string | undefined>(undefined);
  const categoriesSectionRef = useRef<HTMLDivElement | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();

  // Lien profond depuis « Voir la dépense » (détail d'un mouvement de stock,
  // fiche `logistique.md` §4.3) : ouvre directement le détail de la dépense.
  useEffect(() => {
    const raw = searchParams.get("depense");
    if (!raw) return;
    const id = Number(raw);
    if (Number.isFinite(id)) setDetailExpenseId(id);
    const next = new URLSearchParams(searchParams);
    next.delete("depense");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const profileQuery = useQuery({ queryKey: ["profile", "me"], queryFn: getMyProfile, staleTime: 60_000 });
  const capabilitiesQuery = useQuery({ queryKey: CAPABILITIES_QUERY_KEY, queryFn: getTreasuryCapabilities });
  const capabilities = capabilitiesQuery.data?.capabilities;
  const currency = capabilitiesQuery.data?.currency ?? "";
  const canRead = capabilities?.can_read_expenses ?? false;

  const summaryQuery = useQuery({ queryKey: SUMMARY_QUERY_KEY, queryFn: getExpenseSummary, enabled: canRead });

  const pendingQuery = useQuery({
    queryKey: ["treasury", "expenses", "pending", pendingLimit],
    queryFn: () => getExpenses({ status: PENDING_STATUSES, limit: pendingLimit }),
    enabled: canRead,
  });
  const recentQuery = useQuery({
    queryKey: ["treasury", "expenses", "recent", recentLimit],
    queryFn: () => getExpenses({ status: RECENT_STATUSES, limit: recentLimit }),
    enabled: canRead,
  });
  const categoriesQuery = useQuery({
    queryKey: CATEGORIES_QUERY_KEY,
    queryFn: () => getExpenseCategories("active"),
    enabled: canRead,
  });

  const totalExpenses = (pendingQuery.data?.count ?? 0) + (recentQuery.data?.count ?? 0);

  function invalidateExpenseLists(): void {
    void queryClient.invalidateQueries({ queryKey: ["treasury", "expenses"] });
    void queryClient.invalidateQueries({ queryKey: SUMMARY_QUERY_KEY });
  }

  function handleSeeMore(section: "pending" | "recent"): void {
    if (totalExpenses > EXPANDED_THRESHOLD) {
      setExpandedView(true);
      return;
    }
    if (section === "pending") setPendingLimit((l) => l + PAGE_STEP);
    else setRecentLimit((l) => l + PAGE_STEP);
  }

  const createExpenseMutation = useMutation({
    mutationFn: (values: CreateExpenseFormValues) =>
      createExpense({
        category_id: values.categoryId,
        amount: values.amount,
        beneficiary_name: values.beneficiaryName,
        beneficiary_membership_id: values.beneficiaryMembershipId,
        reason: values.reason,
        expense_date: values.expenseDate,
        attachment: values.attachment,
      }),
    onSuccess: () => {
      invalidateExpenseLists();
      setShowCreateExpense(false);
      setCreateError(undefined);
      showToast("Dépense enregistrée.");
    },
    onError: (error) => setCreateError(apiErrorMessage(error, "Une erreur est survenue de notre côté. Réessayez.")),
  });

  const categorySaveMutation = useMutation({
    mutationFn: (input: ExpenseCategoryInput) =>
      editingCategory ? updateExpenseCategory(editingCategory.id, input) : createExpenseCategory(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CATEGORIES_QUERY_KEY });
      setShowCategoryForm(false);
      setEditingCategory(undefined);
      showToast("Catégorie enregistrée.");
    },
  });

  const categoryArchiveMutation = useMutation({
    mutationFn: (category: ExpenseCategory) => archiveExpenseCategory(category.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CATEGORIES_QUERY_KEY });
      setArchiveTarget(null);
      setDetailCategory(null);
      showToast("Catégorie archivée.");
    },
  });

  function openCreateCategory(): void {
    categorySaveMutation.reset();
    setEditingCategory(undefined);
    setShowCategoryForm(true);
  }

  function scrollToCategories(): void {
    categoriesSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function openEditCategory(category: ExpenseCategory): void {
    categorySaveMutation.reset();
    setEditingCategory(category);
    setDetailCategory(null);
    setShowCategoryForm(true);
  }

  if (profileQuery.isLoading || capabilitiesQuery.isLoading) return <Loader loading variant="page" />;
  if (profileQuery.isError || capabilitiesQuery.isError) {
    return (
      <EmptyState
        variant="error"
        actionLabel="Réessayer"
        onAction={() => {
          void profileQuery.refetch();
          void capabilitiesQuery.refetch();
        }}
      />
    );
  }
  if (!canRead || !capabilities) {
    return <EmptyState message="Vous n'avez pas accès aux dépenses." />;
  }

  const clubName = profileQuery.data?.club.name ?? "";
  const blockingId = summaryQuery.data?.blocking_expense_ids[0];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">Dépenses</h1>
          <p className="text-sm text-text-muted">{clubName}</p>
        </div>
        <div className="flex items-center gap-2">
          {capabilities.can_submit_expenses ? (
            <Button variant="primary" size="sm" onClick={() => setShowCreateExpense(true)}>
              Saisir une dépense
            </Button>
          ) : null}
          {capabilities.can_manage_expense_categories ? (
            <KebabMenu items={[{ label: "Gérer les catégories", onSelect: scrollToCategories }]} />
          ) : null}
        </div>
      </header>

      {summaryQuery.data && !summaryQuery.data.can_release ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-status-danger-bg px-3 py-2 text-sm text-status-danger-fg"
        >
          <span>{summaryQuery.data.reason}</span>
          {blockingId ? (
            <button type="button" className="-my-2 py-2 font-medium underline" onClick={() => setDetailExpenseId(blockingId)}>
              Voir la dépense
            </button>
          ) : null}
        </div>
      ) : null}

      {expandedView ? (
        <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
          <h2 className="mb-3 text-base font-semibold text-text">Toutes les dépenses</h2>
          <AllExpensesTable onOpen={setDetailExpenseId} />
        </section>
      ) : (
        <>
          <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
            <h2 className="mb-3 text-base font-semibold text-text">À traiter</h2>
            {pendingQuery.isLoading ? (
              <Loader loading variant="list" count={5} />
            ) : pendingQuery.isError ? (
              <EmptyState
                variant="error"
                message="Impossible de charger les dépenses à traiter."
                actionLabel="Réessayer"
                onAction={() => void pendingQuery.refetch()}
              />
            ) : (pendingQuery.data?.results.length ?? 0) === 0 ? (
              <EmptyState message="Aucune dépense à traiter." />
            ) : (
              <>
                <div className="divide-y divide-border">
                  {pendingQuery.data!.results.map((expense) => (
                    <ExpenseRow key={expense.id} expense={expense} showStatus={false} onOpen={setDetailExpenseId} />
                  ))}
                </div>
                {pendingQuery.data!.results.length < (pendingQuery.data!.count ?? 0) ? (
                  <div className="mt-2 text-center">
                    <Button variant="secondary" size="sm" onClick={() => handleSeeMore("pending")}>
                      Voir plus
                    </Button>
                  </div>
                ) : null}
              </>
            )}
          </section>

          <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
            <h2 className="mb-3 text-base font-semibold text-text">Dépenses récentes</h2>
            {recentQuery.isLoading ? (
              <Loader loading variant="list" count={5} />
            ) : recentQuery.isError ? (
              <EmptyState
                variant="error"
                message="Impossible de charger les dépenses."
                actionLabel="Réessayer"
                onAction={() => void recentQuery.refetch()}
              />
            ) : (recentQuery.data?.results.length ?? 0) === 0 ? (
              <EmptyState
                message="Aucune dépense enregistrée pour l'instant."
                actionLabel={capabilities.can_submit_expenses ? "Saisir une dépense" : undefined}
                onAction={capabilities.can_submit_expenses ? () => setShowCreateExpense(true) : undefined}
              />
            ) : (
              <>
                <div className="divide-y divide-border">
                  {recentQuery.data!.results.map((expense) => (
                    <ExpenseRow key={expense.id} expense={expense} showStatus onOpen={setDetailExpenseId} />
                  ))}
                </div>
                {recentQuery.data!.results.length < (recentQuery.data!.count ?? 0) ? (
                  <div className="mt-2 text-center">
                    <Button variant="secondary" size="sm" onClick={() => handleSeeMore("recent")}>
                      Voir plus
                    </Button>
                  </div>
                ) : null}
              </>
            )}
          </section>
        </>
      )}

      <section ref={categoriesSectionRef} className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-text">Catégories</h2>
          {capabilities.can_manage_expense_categories ? (
            <Button variant="secondary" size="sm" onClick={openCreateCategory}>
              Créer une catégorie
            </Button>
          ) : null}
        </div>
        {categoriesQuery.isLoading ? (
          <Loader loading variant="list" count={3} />
        ) : categoriesQuery.isError ? (
          <EmptyState
            variant="error"
            message="Impossible de charger les catégories."
            actionLabel="Réessayer"
            onAction={() => void categoriesQuery.refetch()}
          />
        ) : (categoriesQuery.data?.length ?? 0) === 0 ? (
          <EmptyState
            message="Aucune catégorie de dépense."
            actionLabel={capabilities.can_manage_expense_categories ? "Créer une catégorie" : undefined}
            onAction={capabilities.can_manage_expense_categories ? openCreateCategory : undefined}
          />
        ) : (
          <div className="divide-y divide-border">
            {categoriesQuery.data!.map((category) => (
              <CategoryRow key={category.id} category={category} currency={currency} onOpen={setDetailCategory} />
            ))}
          </div>
        )}
      </section>

      <ExpenseDetailModal
        expenseId={detailExpenseId}
        capabilities={capabilities}
        onClose={() => setDetailExpenseId(null)}
        onChanged={invalidateExpenseLists}
      />

      <CreateExpenseModal
        open={showCreateExpense}
        currency={currency}
        isSubmitting={createExpenseMutation.isPending}
        submitError={createError}
        onClose={() => setShowCreateExpense(false)}
        onSubmit={(values) => createExpenseMutation.mutate(values)}
      />

      {showCategoryForm ? (
        <ExpenseCategoryModal
          key={editingCategory?.id ?? "new"}
          open
          category={editingCategory}
          currency={currency}
          isSubmitting={categorySaveMutation.isPending}
          submitError={categorySaveMutation.isError ? apiErrorMessage(categorySaveMutation.error, "Une erreur est survenue de notre côté. Réessayez.") : undefined}
          onClose={() => {
            setShowCategoryForm(false);
            setEditingCategory(undefined);
          }}
          onSubmit={(input) => categorySaveMutation.mutate(input)}
        />
      ) : null}

      <ExpenseCategoryDetailModal
        category={detailCategory}
        currency={currency}
        canEdit={capabilities.can_manage_expense_categories}
        onClose={() => setDetailCategory(null)}
        onEdit={openEditCategory}
        onArchive={(category) => setArchiveTarget(category)}
      />

      <ConfirmDialog
        open={archiveTarget !== null}
        title="Archiver cette catégorie ?"
        confirmLabel="Archiver"
        loading={categoryArchiveMutation.isPending}
        onCancel={() => setArchiveTarget(null)}
        onConfirm={() => archiveTarget && categoryArchiveMutation.mutate(archiveTarget)}
      />
    </div>
  );
}
