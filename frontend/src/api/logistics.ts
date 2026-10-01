/**
 * Appels de l'app `logistics` (Lot 4, tâche 4.13 ; fiche `docs/ecrans/logistique.md`).
 * Contrats lus directement dans `backend/apps/logistics/{urls,views,serializers}.py` :
 * aucune forme n'est devinée ici.
 */

import { apiGet, apiPost, apiPatch } from "./client";
import type { ArticleSearchResult } from "../design-system/components/ArticleSearch";

export type ArticleCategory = "jersey" | "socks" | "cleats" | "balls" | "misc";
export type ArticleCondition = "new" | "good" | "worn" | "damaged";
export type ArticleStatus = "active" | "archived";

export type MovementType =
  | "in_purchase"
  | "in_donation"
  | "in_return"
  | "out_distribution"
  | "out_loan"
  | "out_wear"
  | "out_loss";

export const IN_MOVEMENT_TYPES: MovementType[] = ["in_purchase", "in_donation", "in_return"];
export const OUT_MOVEMENT_TYPES: MovementType[] = ["out_distribution", "out_loan", "out_wear", "out_loss"];

export type DiscrepancyReason = "theft" | "wear" | "oversight" | "loss";

export interface ActorBrief {
  id: number | null;
  name: string;
}

export interface Article {
  id: number;
  name: string;
  category: ArticleCategory;
  category_display: string;
  unit: string;
  reference_condition: ArticleCondition;
  reference_condition_display: string;
  status: ArticleStatus;
  in_stock: number;
  loaned_for_match: number;
  created_at: string;
  created_by: ActorBrief;
}

export interface ArticleInput {
  name: string;
  category: ArticleCategory;
  unit?: string;
  reference_condition?: ArticleCondition;
}

export interface ListArticlesParams {
  include_archived?: boolean;
  category?: ArticleCategory;
  condition?: ArticleCondition;
  search?: string;
}

export function listArticles(params: ListArticlesParams = {}) {
  const qs = new URLSearchParams();
  if (params.include_archived) qs.set("include_archived", "true");
  if (params.category) qs.set("category", params.category);
  if (params.condition) qs.set("condition", params.condition);
  if (params.search) qs.set("search", params.search);
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<{ count: number; results: Article[] }>(`/logistics/articles/${suffix}`);
}

export function createArticle(input: ArticleInput) {
  return apiPost<Article>("/logistics/articles/", input);
}

export function getArticle(id: number) {
  return apiGet<Article>(`/logistics/articles/${id}/`);
}

export function updateArticle(id: number, input: ArticleInput) {
  return apiPatch<Article>(`/logistics/articles/${id}/`, input);
}

export function archiveArticle(id: number) {
  return apiPost<Article>(`/logistics/articles/${id}/`, { action: "archive" });
}

export function reactivateArticle(id: number) {
  return apiPost<Article>(`/logistics/articles/${id}/`, { action: "reactivate" });
}

export interface StockMovement {
  id: number;
  article: { id: number; name: string; unit: string };
  movement_type: MovementType;
  movement_type_display: string;
  quantity: number;
  signed_quantity: number;
  movement_date: string;
  reason: string;
  membership: { id: number; name: string } | null;
  match_id: number | null;
  expense_id: number | null;
  recorded_by: ActorBrief;
  created_at: string;
}

export interface ListMovementsParams {
  article?: number;
  movement_type?: MovementType;
  sense?: "in" | "out";
  match?: number;
  expense?: number;
}

export function listMovements(params: ListMovementsParams = {}) {
  const qs = new URLSearchParams();
  if (params.article) qs.set("article", String(params.article));
  if (params.movement_type) qs.set("movement_type", params.movement_type);
  if (params.sense) qs.set("sense", params.sense);
  if (params.match) qs.set("match", String(params.match));
  if (params.expense) qs.set("expense", String(params.expense));
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<{ count: number; results: StockMovement[] }>(`/logistics/movements/${suffix}`);
}

export function getMovement(id: number) {
  return apiGet<StockMovement>(`/logistics/movements/${id}/`);
}

export interface MovementInput {
  movement_type: MovementType;
  article_id: number;
  quantity: number;
  movement_date: string;
  reason?: string;
  membership_id?: number | null;
  match_id?: number | null;
  expense_id?: number | null;
}

export function recordMovement(input: MovementInput) {
  return apiPost<{ movement: StockMovement; in_stock: number }>("/logistics/movements/", input);
}

// ---------------------------------------------------------------------------
// Équipements d'un match (CDC 4.8, 4.13)
// ---------------------------------------------------------------------------

export type MatchEquipmentLineStatus = "out" | "partially_returned" | "returned";

export interface MatchEquipmentLine {
  article_id: number;
  article_name: string | null;
  out_quantity: number;
  returned_quantity: number;
  remaining_quantity: number;
  status: MatchEquipmentLineStatus;
}

export function getMatchEquipment(matchId: number) {
  return apiGet<{ lines: MatchEquipmentLine[] }>(`/logistics/matches/${matchId}/equipment/`);
}

export function recordMatchEquipmentOut(matchId: number, lines: Array<{ article_id: number; quantity: number }>) {
  return apiPost<{ lines: MatchEquipmentLine[] }>(`/logistics/matches/${matchId}/equipment/out/`, { lines });
}

export function recordMatchEquipmentReturn(
  matchId: number,
  lines: Array<{ article_id: number; quantity_returned: number }>,
  observation?: string,
) {
  return apiPost<{ lines: MatchEquipmentLine[] }>(`/logistics/matches/${matchId}/equipment/return/`, {
    lines,
    observation,
  });
}

// ---------------------------------------------------------------------------
// Inventaire trimestriel (CDC 4.13)
// ---------------------------------------------------------------------------

export type InventoryStatus = "open" | "closed";
export type InventoryLineStatus = "no_gap" | "justified" | "to_justify";

export interface InventoryLine {
  id: number;
  article_id: number;
  article_name: string;
  theoretical_quantity: number;
  physical_quantity: number;
  discrepancy: number;
  discrepancy_reason: DiscrepancyReason | "";
  status: InventoryLineStatus;
  justified_by_id: number | null;
  justified_at: string | null;
}

export interface Inventory {
  id: number;
  quarter_label: string;
  quarter_label_display: string;
  status: InventoryStatus;
  opened_at: string;
  opened_by: ActorBrief;
  closed_at: string | null;
  closed_by: ActorBrief | null;
  lines?: InventoryLine[];
}

export interface MaterialOverview {
  current_quarter_label: string;
  current_quarter_label_display: string;
  open_inventory: Inventory | null;
  blocking_inventory: boolean;
  to_count: number;
  to_justify: number;
  counted: number;
  total_active_articles: number;
  can_open: boolean;
  openable_quarter_label: string | null;
  openable_quarter_label_display: string | null;
  last_closed_inventory: Inventory | null;
}

export function getMaterialOverview() {
  return apiGet<MaterialOverview>("/logistics/overview/");
}

export function openInventory() {
  return apiPost<Inventory>("/logistics/inventories/open/");
}

export function getInventory(id: number) {
  return apiGet<Inventory>(`/logistics/inventories/${id}/`);
}

export function recordInventoryCounts(id: number, counts: Array<{ article_id: number; physical_quantity: number }>) {
  return apiPost<{ lines_counted: number; to_justify: number; inventory: Inventory }>(
    `/logistics/inventories/${id}/counts/`,
    { counts },
  );
}

export function justifyInventoryLine(lineId: number, discrepancyReason: DiscrepancyReason) {
  return apiPost<InventoryLine>(`/logistics/inventory-lines/${lineId}/justify/`, {
    discrepancy_reason: discrepancyReason,
  });
}

export function closeInventory(id: number) {
  return apiPost<Inventory>(`/logistics/inventories/${id}/close/`);
}

// ---------------------------------------------------------------------------
// `ArticleSearch` (design-system §4.8) : adaptation du catalogue.
// ---------------------------------------------------------------------------

export function toArticleSearchResult(article: Article): ArticleSearchResult {
  return {
    id: article.id,
    name: article.name,
    categoryLabel: article.category_display,
    unit: article.unit,
    inStock: article.in_stock,
  };
}

/** Articles actifs du club, prêts pour `ArticleSearch` (§4.4, §4.5). */
export function searchArticles(query: string): Promise<ArticleSearchResult[]> {
  return listArticles({ search: query }).then((response) => response.results.map(toArticleSearchResult));
}
