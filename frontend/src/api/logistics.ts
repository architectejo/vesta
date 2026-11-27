/**
 * Appels de l'app `logistics` (Lot 4, tâche 4.13 ; fiches `docs/ecrans/logistique.md`
 * et `docs/ecrans/logistique-intendance-registre.md`).
 * Contrats lus directement dans `backend/apps/logistics/{urls,views,serializers,register}.py` :
 * aucune forme n'est devinée ici.
 */

import { apiDownload, apiGet, apiPatch, apiPost, triggerBlobDownload } from "./client";
import type { ArticleSearchResult } from "../design-system/components/ArticleSearch";

export type ArticleCategory =
  | "jersey"
  | "socks"
  | "cleats"
  | "balls"
  | "misc"
  | "shorts"
  | "bibs"
  | "referee"
  | "accessories"
  | "furniture";
export type ArticleCondition = "new" | "good" | "worn" | "damaged" | "unknown";
export type ArticleStatus = "active" | "archived";

export type MovementType =
  | "in_purchase"
  | "in_donation"
  | "in_return"
  | "out_distribution"
  | "out_loan"
  | "out_wear"
  | "out_loss"
  | "in_opening"
  | "in_transfer"
  | "out_transfer"
  | "out_decommission";

export const IN_MOVEMENT_TYPES: MovementType[] = ["in_purchase", "in_donation", "in_return", "in_opening", "in_transfer"];
export const OUT_MOVEMENT_TYPES: MovementType[] = [
  "out_distribution",
  "out_loan",
  "out_wear",
  "out_loss",
  "out_transfer",
  "out_decommission",
];

/** Types saisissables par `POST movements/` (`StockMovement.MANUAL_TYPES`) :
 * transferts et déclassements ont leur propre point d'API. */
export type ManualMovementType =
  | "in_purchase"
  | "in_donation"
  | "in_return"
  | "in_opening"
  | "out_distribution"
  | "out_loan"
  | "out_wear"
  | "out_loss";

/** Entrées portant une provenance (`StockMovement.PROVENANCE_TYPES`). */
export const PROVENANCE_MOVEMENT_TYPES: MovementType[] = ["in_purchase", "in_donation", "in_opening"];

export type DiscrepancyReason = "theft" | "wear" | "oversight" | "loss";

export interface ActorBrief {
  id: number | null;
  name: string;
}

export type HolderKind = "member" | "place";

/** Référence courte d'un détenteur (`_holder_ref` côté API). */
export interface HolderRef {
  id: number;
  name: string;
  kind: HolderKind;
}

/** Ligne de répartition du stock ; `holder_id: null` = « Non localisé ». */
export interface StockRow {
  holder_id: number | null;
  holder: HolderRef | null;
  holder_name: string;
  quantity: number;
}

export type OriginKind = "donation" | "club_funds" | "unknown";

export interface Provenance {
  movement_id: number;
  quantity: number;
  movement_type: MovementType;
  origin_kind: OriginKind | "";
  /** « Origine non renseignée » si `origin_kind` est vide (API). */
  origin_kind_display: string;
  donor: { membership_id: number | null; name: string } | null;
  acquisition_date: string | null;
  acquisition_date_unknown: boolean;
  acquisition_date_note: string;
  condition_at_entry: ArticleCondition | "";
  condition_at_entry_display: string;
  holder: HolderRef | null;
  movement_date: string;
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
  /** Lignes à 0 exclues ; tri par quantité décroissante, « Non localisé » en dernier. */
  stock_by_holder: StockRow[];
  pending_decommission: number;
  suggested_holder: HolderRef | null;
  /** Seulement dans `GET articles/{id}/` (5 au plus). */
  provenances?: Provenance[];
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
  holder: HolderRef | null;
  provenance: Provenance | null;
  transfer_group: string | null;
  decommission_id: number | null;
  recorded_by: ActorBrief;
  created_at: string;
}

export interface ListMovementsParams {
  article?: number;
  movement_type?: MovementType;
  sense?: "in" | "out";
  match?: number;
  expense?: number;
  /** Identifiant d'un détenteur, ou « none » pour « Non localisé ». */
  holder?: number | "none";
  /** Plusieurs types, envoyés en CSV. */
  types?: MovementType[];
  /** 50 par défaut, 200 au plus (API). */
  limit?: number;
  offset?: number;
}

export interface MovementPage {
  /** Total filtré, pas seulement la page. */
  count: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  results: StockMovement[];
}

export function listMovements(params: ListMovementsParams = {}) {
  const qs = new URLSearchParams();
  if (params.article) qs.set("article", String(params.article));
  if (params.movement_type) qs.set("movement_type", params.movement_type);
  if (params.sense) qs.set("sense", params.sense);
  if (params.match) qs.set("match", String(params.match));
  if (params.expense) qs.set("expense", String(params.expense));
  if (params.holder !== undefined) qs.set("holder", String(params.holder));
  if (params.types && params.types.length > 0) qs.set("types", params.types.join(","));
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<MovementPage>(`/logistics/movements/${suffix}`);
}

export function getMovement(id: number) {
  return apiGet<StockMovement>(`/logistics/movements/${id}/`);
}

export interface ProvenanceInput {
  origin_kind?: OriginKind;
  donor_membership_id?: number;
  /** 120 caractères au plus. */
  donor_name?: string;
  acquisition_date?: string;
  acquisition_date_unknown?: boolean;
  /** 60 caractères au plus ; seulement avec une date inconnue. */
  acquisition_date_note?: string;
  condition_at_entry?: ArticleCondition;
}

export interface MovementInput {
  movement_type: ManualMovementType;
  article_id: number;
  quantity: number;
  /** « AAAA-MM-JJ ». */
  movement_date: string;
  /** 500 caractères au plus. */
  reason?: string;
  membership_id?: number | null;
  match_id?: number | null;
  /** Seulement sur un Achat. */
  expense_id?: number | null;
  /** Absent = Non localisé à l'entrée ; `null` = « Non localisé » explicite. */
  holder_id?: number | null;
  provenance?: ProvenanceInput | null;
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
  /** Détenteur de la sortie ; destination par défaut du retour. */
  holder: HolderRef | null;
}

/** `holder_id` absent = sortie depuis le `suggested_holder` de l'article ;
 * `null` = « Non localisé ». 50 lignes au plus. */
export interface MatchEquipmentOutLine {
  article_id: number;
  quantity: number;
  holder_id?: number | null;
}

export interface MatchEquipmentReturnLine {
  article_id: number;
  quantity_returned: number;
  holder_id?: number | null;
}

export function getMatchEquipment(matchId: number) {
  return apiGet<{ lines: MatchEquipmentLine[] }>(`/logistics/matches/${matchId}/equipment/`);
}

export function recordMatchEquipmentOut(matchId: number, lines: MatchEquipmentOutLine[]) {
  return apiPost<{ lines: MatchEquipmentLine[] }>(`/logistics/matches/${matchId}/equipment/out/`, { lines });
}

export function recordMatchEquipmentReturn(
  matchId: number,
  lines: MatchEquipmentReturnLine[],
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
// Détenteurs et déplacements (registre de l'intendance, lot 2)
// ---------------------------------------------------------------------------

export interface Holder {
  id: number;
  kind: HolderKind;
  kind_display: string;
  name: string;
  membership_id: number | null;
  label: string;
  status: "active" | "archived";
  has_left_club: boolean;
  stock_total: number;
  articles_count: number;
  created_at: string;
}

export interface HolderList {
  count: number;
  results: Holder[];
  unlocated: { stock_total: number; articles_count: number };
}

export interface HolderArticle {
  article_id: number;
  name: string;
  category: ArticleCategory;
  category_display: string;
  unit: string;
  quantity: number;
  pending_decommission: number;
}

export interface HolderDetail extends Holder {
  articles: HolderArticle[];
  recent_movements: StockMovement[];
}

export function listHolders(includeArchived = false) {
  return apiGet<HolderList>(`/logistics/holders/${includeArchived ? "?include_archived=true" : ""}`);
}

export function getHolder(id: number) {
  return apiGet<HolderDetail>(`/logistics/holders/${id}/`);
}

export interface HolderInput {
  kind: HolderKind;
  membership_id?: number;
  label?: string;
}

export function createHolder(input: HolderInput) {
  return apiPost<Holder>("/logistics/holders/", input);
}

export function renameHolder(id: number, label: string) {
  return apiPatch<HolderDetail>(`/logistics/holders/${id}/`, { label });
}

export function archiveHolder(id: number) {
  return apiPost<Holder>(`/logistics/holders/${id}/archive/`);
}

export interface TransferInput {
  article_id: number;
  /** `null` = « Non localisé ». */
  from_holder_id: number | null;
  to_holder_id: number | null;
  quantity: number;
  movement_date: string;
  reason?: string;
}

export interface TransferResult {
  transfer_group: string;
  out_movement: StockMovement;
  in_movement: StockMovement;
  in_stock: number;
  stock_by_holder: StockRow[];
}

export function createTransfer(input: TransferInput) {
  return apiPost<TransferResult>("/logistics/transfers/", input);
}

// ---------------------------------------------------------------------------
// Déclassement (lot 4)
// ---------------------------------------------------------------------------

export type DecommissionReason = "worn" | "damaged" | "unusable" | "other";
export type DecommissionStatus = "pending" | "done" | "cancelled";

export interface Decommission {
  id: number;
  article: { id: number; name: string; unit: string; category: ArticleCategory };
  holder: HolderRef | null;
  quantity: number;
  reason: DecommissionReason;
  reason_display: string;
  reason_note: string;
  noted_on: string;
  noted_by: ActorBrief | null;
  status: DecommissionStatus;
  status_display: string;
  exit_date: string | null;
  exit_destination: string;
  exit_movement_id: number | null;
  executed_by: ActorBrief | null;
  cancelled_at: string | null;
  cancelled_by: ActorBrief | null;
  cancel_reason: string;
  created_at: string;
}

export interface DecommissionList {
  count: number;
  /** Quantité totale en attente de sortie, tous articles confondus. */
  pending_quantity: number;
  results: Decommission[];
}

/** 200 résultats au plus, sans pagination (API). */
export function listDecommissions(params: { status?: DecommissionStatus; article?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.article) qs.set("article", String(params.article));
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<DecommissionList>(`/logistics/decommissions/${suffix}`);
}

export function getDecommission(id: number) {
  return apiGet<Decommission>(`/logistics/decommissions/${id}/`);
}

export interface DecommissionInput {
  article_id: number;
  holder_id?: number | null;
  quantity: number;
  reason: DecommissionReason;
  reason_note?: string;
  noted_on: string;
}

export function flagDecommission(input: DecommissionInput) {
  return apiPost<Decommission>("/logistics/decommissions/", input);
}

/** `destination` en entrée, `exit_destination` en lecture (API). */
export function executeDecommission(id: number, input: { exit_date: string; destination?: string }) {
  return apiPost<{ decommission: Decommission; in_stock: number }>(`/logistics/decommissions/${id}/execute/`, {
    ...input,
    confirm: true,
  });
}

export function cancelDecommission(id: number, reason: string) {
  return apiPost<Decommission>(`/logistics/decommissions/${id}/cancel/`, { reason });
}

// ---------------------------------------------------------------------------
// Registre de l'intendance (lot 5)
// ---------------------------------------------------------------------------

export interface RegisterParams {
  search?: string;
  category?: ArticleCategory;
  holder?: number | "none";
  include_exits?: boolean;
}

export interface RegisterLine {
  movement_id: number;
  article_id: number;
  designation: string;
  category: ArticleCategory;
  category_display: string;
  unit: string;
  quantity: number;
  /** « 1 pièce », « 26 pièces » : quantité et unité accordées par l'API. */
  quantity_label: string;
  movement_type: MovementType;
  origin_kind: OriginKind | "";
  donor_name: string;
  origin: string;
  acquisition_date: string | null;
  acquisition_date_unknown: boolean;
  acquisition_date_note: string;
  acquisition_label: string;
  recorded_on: string;
  holder_id: number | null;
  location: string;
  condition: ArticleCondition;
  condition_display: string;
}

export interface RegisterSection {
  category: ArticleCategory;
  category_display: string;
  lines: RegisterLine[];
  stock_total_by_unit: Array<{ unit: string; quantity: number }>;
  /** « Stock actuel : 19 pièces » (stock après sorties, pas la somme des lignes). */
  stock_total_label: string;
  current_distribution: Array<{ holder_id: number | null; holder_name: string; quantity: number }>;
}

export interface RegisterDecommission {
  id: number;
  article_id: number;
  designation: string;
  unit: string;
  quantity: number;
  /** « 1 pièce », « 26 pièces » : quantité et unité accordées par l'API. */
  quantity_label: string;
  reason: DecommissionReason;
  reason_display: string;
  reason_note: string;
  holder_id: number | null;
  location: string;
  noted_on: string;
}

export interface RegisterExit {
  movement_id: number;
  designation: string;
  unit: string;
  quantity: number;
  /** « 1 pièce », « 26 pièces » : quantité et unité accordées par l'API. */
  quantity_label: string;
  movement_type: MovementType;
  movement_type_display: string;
  movement_date: string;
  location: string;
  reason: string;
}

export interface RegisterFilters {
  search: string;
  category: ArticleCategory | "";
  holder: number | "none" | null;
  include_exits: boolean;
}

export interface Register {
  club: { id: number; name: string };
  as_of: string;
  /** Filtres appliqués, tels que relus par l'API (aussi écrits au journal). */
  filters: RegisterFilters;
  filters_label: string;
  include_exits: boolean;
  sections: RegisterSection[];
  decommissions: RegisterDecommission[];
  exits: RegisterExit[];
  is_empty: boolean;
}

/** Chaîne de requête du registre, partagée par la page et les téléchargements. */
export function registerQueryString(params: RegisterParams): string {
  const qs = new URLSearchParams();
  if (params.search) qs.set("search", params.search);
  if (params.category) qs.set("category", params.category);
  if (params.holder !== undefined) qs.set("holder", String(params.holder));
  if (params.include_exits) qs.set("include_exits", "true");
  const text = qs.toString();
  return text ? `?${text}` : "";
}

export function getRegister(params: RegisterParams = {}) {
  return apiGet<Register>(`/logistics/register/${registerQueryString(params)}`);
}

/** Le nom du fichier vient de `Content-Disposition` (API). */
export async function downloadRegisterPdf(params: RegisterParams = {}): Promise<void> {
  const { blob, filename } = await apiDownload(
    `/logistics/register/pdf/${registerQueryString(params)}`,
    "registre-intendance.pdf",
  );
  triggerBlobDownload(blob, filename);
}

export async function downloadRegisterCsv(params: RegisterParams = {}): Promise<void> {
  const { blob, filename } = await apiDownload(
    `/logistics/register/csv/${registerQueryString(params)}`,
    "registre-intendance.csv",
  );
  triggerBlobDownload(blob, filename);
}

// ---------------------------------------------------------------------------
// Dépenses rattachables à un achat (10.2 n° 167)
// ---------------------------------------------------------------------------

export interface LinkableExpense {
  id: number;
  reference: string;
  expense_date: string;
  amount: string;
  currency: string;
  category: string;
  status: string;
  status_display: string;
}

/** `GET logistics/expenses/linkable/?q=` ; l'API répond `{count, results}`. */
export function searchLinkableExpenses(query: string): Promise<LinkableExpense[]> {
  const qs = new URLSearchParams();
  if (query.trim()) qs.set("q", query.trim());
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<{ count: number; results: LinkableExpense[] }>(`/logistics/expenses/linkable/${suffix}`).then(
    (response) => response.results,
  );
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
    stockByHolder: article.stock_by_holder,
    suggestedHolder: article.suggested_holder,
    pendingDecommission: article.pending_decommission,
  };
}

/** Articles actifs du club, prêts pour `ArticleSearch` (§4.4, §4.5). */
export function searchArticles(query: string): Promise<ArticleSearchResult[]> {
  return listArticles({ search: query }).then((response) => response.results.map(toArticleSearchResult));
}
