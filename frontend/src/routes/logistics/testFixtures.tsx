/** Fixtures et rendu partagés par les tests du module logistique. */
import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type {
  Article,
  Decommission,
  Holder,
  HolderList,
  MovementPage,
  StockMovement,
  StockRow,
} from "../../api/logistics";
import type { ArticleSearchResult } from "../../design-system";
import { ToastProvider } from "../../design-system";

export function renderWithProviders(ui: ReactElement, { route = "/" }: { route?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...result, client };
}

export function makeHolder(over: Partial<Holder> = {}): Holder {
  return {
    id: 1,
    kind: "place",
    kind_display: "Lieu",
    name: "Local du club",
    membership_id: null,
    label: "Local du club",
    status: "active",
    has_left_club: false,
    stock_total: 10,
    articles_count: 2,
    created_at: "2026-10-01T10:00:00Z",
    ...over,
  };
}

export function makeHolderList(results: Holder[], unlocated = 0): HolderList {
  return { count: results.length, results, unlocated: { stock_total: unlocated, articles_count: unlocated ? 1 : 0 } };
}

export function stockRow(holderId: number | null, name: string, quantity: number): StockRow {
  return {
    holder_id: holderId,
    holder: holderId === null ? null : { id: holderId, name, kind: "place" },
    holder_name: name,
    quantity,
  };
}

export function makeArticle(over: Partial<Article> = {}): Article {
  return {
    id: 10,
    name: "Maillot domicile",
    category: "jersey",
    category_display: "Maillots",
    unit: "pièce",
    reference_condition: "good",
    reference_condition_display: "Bon état",
    status: "active",
    in_stock: 12,
    loaned_for_match: 0,
    stock_by_holder: [stockRow(1, "Local du club", 8), stockRow(null, "Non localisé", 4)],
    pending_decommission: 0,
    suggested_holder: { id: 1, name: "Local du club", kind: "place" },
    created_at: "2026-10-01T10:00:00Z",
    created_by: { id: 3, name: "Paul Intendant" },
    ...over,
  };
}

export function toSearchResult(article: Article): ArticleSearchResult {
  return {
    id: article.id,
    name: article.name,
    categoryLabel: article.category_display,
    unit: article.unit,
    inStock: article.in_stock,
    stockByHolder: article.stock_by_holder,
    suggestedHolder: article.suggested_holder,
    pendingDecommission: article.pending_decommission,
  };
}

export function makeMovement(id: number, over: Partial<StockMovement> = {}): StockMovement {
  return {
    id,
    article: { id: 10, name: "Maillot domicile", unit: "pièce" },
    movement_type: "in_purchase",
    movement_type_display: "Achat",
    quantity: 2,
    signed_quantity: 2,
    movement_date: "2026-10-10",
    reason: "",
    membership: null,
    match_id: null,
    expense_id: null,
    holder: { id: 1, name: "Local du club", kind: "place" },
    provenance: null,
    transfer_group: null,
    decommission_id: null,
    recorded_by: { id: 3, name: "Paul Intendant" },
    created_at: "2026-10-10T10:00:00Z",
    ...over,
  };
}

export function movementPage(results: StockMovement[], nextOffset: number | null, count: number, offset = 0): MovementPage {
  return { count, limit: 50, offset, next_offset: nextOffset, results };
}

export function makeDecommission(over: Partial<Decommission> = {}): Decommission {
  return {
    id: 7,
    article: { id: 10, name: "Maillot domicile", unit: "pièce", category: "jersey" },
    holder: { id: 1, name: "Local du club", kind: "place" },
    quantity: 3,
    reason: "worn",
    reason_display: "Usé",
    reason_note: "",
    noted_on: "2026-11-01",
    noted_by: { id: 3, name: "Paul Intendant" },
    status: "pending",
    status_display: "À déclasser",
    exit_date: null,
    exit_destination: "",
    exit_movement_id: null,
    executed_by: null,
    cancelled_at: null,
    cancelled_by: null,
    cancel_reason: "",
    created_at: "2026-11-01T10:00:00Z",
    ...over,
  };
}
