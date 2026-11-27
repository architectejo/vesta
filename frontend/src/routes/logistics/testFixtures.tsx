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
  Register,
  RegisterDecommission,
  RegisterExit,
  RegisterLine,
  RegisterSection,
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

// ---------------------------------------------------------------------------
// Registre de l'intendance (`GET /logistics/register/`) : libellés accordés
// fournis par l'API (`quantity_label`, `stock_total_label`).
// ---------------------------------------------------------------------------

export function makeRegisterLine(over: Partial<RegisterLine> = {}): RegisterLine {
  return {
    movement_id: 31,
    article_id: 11,
    designation: "Ballon match",
    category: "balls",
    category_display: "Ballons",
    unit: "pièce",
    quantity: 2,
    quantity_label: "2 pièces",
    movement_type: "in_donation",
    origin_kind: "donation",
    donor_name: "Papa Wemba",
    origin: "Don de Papa Wemba",
    acquisition_date: "2025-06-22",
    acquisition_date_unknown: false,
    acquisition_date_note: "",
    acquisition_label: "22/06/2025",
    recorded_on: "2026-10-01",
    holder_id: 1,
    location: "Local du club",
    condition: "good",
    condition_display: "Bon état",
    ...over,
  };
}

export function makeRegisterSection(over: Partial<RegisterSection> = {}): RegisterSection {
  return {
    category: "balls",
    category_display: "Ballons",
    lines: [makeRegisterLine()],
    stock_total_by_unit: [
      { unit: "pièce", quantity: 22 },
      { unit: "paire", quantity: 23 },
    ],
    stock_total_label: "Stock actuel : 22 pièces · 23 paires",
    current_distribution: [{ holder_id: 1, holder_name: "Local du club", quantity: 14 }],
    ...over,
  };
}

export function makeRegisterDecommission(over: Partial<RegisterDecommission> = {}): RegisterDecommission {
  return {
    id: 7,
    article_id: 10,
    designation: "Maillot domicile",
    unit: "pièce",
    quantity: 1,
    quantity_label: "1 pièce",
    reason: "worn",
    reason_display: "Usé",
    reason_note: "",
    holder_id: 1,
    location: "Local du club",
    noted_on: "2026-11-01",
    ...over,
  };
}

export function makeRegisterExit(over: Partial<RegisterExit> = {}): RegisterExit {
  return {
    movement_id: 40,
    designation: "Chasuble",
    unit: "pièce",
    quantity: 26,
    quantity_label: "26 pièces",
    movement_type: "out_decommission",
    movement_type_display: "Déclassement",
    movement_date: "2026-11-10",
    location: "Local du club",
    reason: "",
    ...over,
  };
}

export function makeRegister(over: Partial<Register> = {}): Register {
  return {
    club: { id: 1, name: "Club de l'API" },
    as_of: "2026-11-26",
    filters: { search: "", category: "", holder: null, include_exits: false },
    filters_label: "",
    include_exits: false,
    sections: [makeRegisterSection()],
    decommissions: [],
    exits: [],
    is_empty: false,
    ...over,
  };
}
