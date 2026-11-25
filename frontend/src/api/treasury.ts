import { apiDownload, apiPatch, apiPost, apiGet, type DownloadResult } from "./client";
import type { PlayerSearchResult } from "../design-system/components/PlayerSearch";

export type ContributionNature = "mandatory" | "free";
export type ContributionPeriodicity = "monthly" | "annual" | "one_off";
export type ContributionScope = "all" | "selected" | "attached";

export interface ContributionType {
  id: number;
  name: string;
  nature: ContributionNature;
  amount: string | null;
  periodicity: ContributionPeriodicity;
  due_day: number | null;
  due_month: number | null;
  deadline: string | null;
  is_membership_fee: boolean;
  scope: ContributionScope;
  status: "active" | "archived";
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContributionTypeInput {
  name: string;
  nature: ContributionNature;
  amount?: string | null;
  periodicity: ContributionPeriodicity;
  due_day?: number | null;
  due_month?: number | null;
  deadline?: string | null;
  is_membership_fee?: boolean;
  scope?: ContributionScope;
}

export function getContributionTypes(status: "active" | "archived" = "active") {
  return apiGet<ContributionType[]>(`/treasury/contribution-types/?status=${status}`);
}

export function createContributionType(input: ContributionTypeInput) {
  return apiPost<ContributionType>("/treasury/contribution-types/", input);
}

export function updateContributionType(id: number, input: Partial<ContributionTypeInput>) {
  return apiPatch<ContributionType>(`/treasury/contribution-types/${id}/`, input);
}

export function archiveContributionType(id: number) {
  return apiPost<ContributionType>(`/treasury/contribution-types/${id}/`, { action: "archive" });
}

// ---------------------------------------------------------------------------
// Capacités de l'utilisateur et devise du club (backend/apps/treasury/views.py
// `TreasuryCapabilitiesView`, tâche 2.2). Remplace, pour les actions ci-dessous,
// la copie locale de la matrice 2.4 de `treasuryAccess.ts`.
// ---------------------------------------------------------------------------

export interface TreasuryCapabilities {
  can_read: boolean;
  can_write: boolean;
  can_record_payments: boolean;
  can_read_expenses: boolean;
  can_manage_expense_categories: boolean;
  can_submit_expenses: boolean;
  can_validate_expenses: boolean;
  can_derogate: boolean;
  can_upload_expense_receipts: boolean;
  can_manage_assistance_scales: boolean;
  can_process_assistance_requests: boolean;
  can_request_assistance: boolean;
  can_decide_payment_reversal: boolean;
}

export interface TreasuryCapabilitiesResponse {
  currency: string;
  capabilities: TreasuryCapabilities;
}

export function getTreasuryCapabilities() {
  return apiGet<TreasuryCapabilitiesResponse>("/treasury/capabilities/");
}

// ---------------------------------------------------------------------------
// Enregistrement des paiements (CDC 4.4.3, 4.4.4) et Caisse Terrain Express
// (CDC 4.4.5, 6.6 ; 10.2 n° 22). Contrats lus dans
// `backend/apps/treasury/{urls,views,serializers}.py` (tâche 2.4).
// ---------------------------------------------------------------------------

export type PaymentMethod = "cash" | "mobile_money" | "payment_link";

export interface BalanceSummary {
  balance: string;
  amount_due: string;
  is_in_good_standing: boolean;
  /** Raison en français, déjà formulée par l'API (ex. « Le joueur est en dette : 20.00 USD à régulariser. »). */
  reason: string;
  currency: string;
}

/** « Mon solde » (club-accueil.md §4.4, carte « Ma situation »). Simple
 * sérialisation du résumé calculé côté API (CLAUDE.md §2.2) : aucun calcul
 * ici, y compris le statut « En ordre »/« En dette » et sa raison. */
export interface MyBalance extends BalanceSummary {
  membership_id: number;
  club_id: number;
}

export function getMyBalance() {
  return apiGet<MyBalance>("/treasury/my-balance/");
}

/** Bouton « Contribuer » (club-accueil.md §4.4) : lien de paiement du club
 * actif, masqué si non configuré (`payment_link_configured`). */
export interface ContributeInfo {
  payment_link_configured: boolean;
  payment_link_url: string | null;
  currency: string;
  contribution_types: Array<{
    id: number;
    name: string;
    nature: ContributionNature;
    periodicity: ContributionPeriodicity;
    amount: string;
  }>;
  default_contribution_type_id: number | null;
}

export function getContributeInfo() {
  return apiGet<ContributeInfo>("/treasury/contribute/");
}

export type AllocationLineStatus = "paid" | "partial" | "free";

export interface PaymentAllocationPreviewLine {
  /** Premier jour du mois concerné (« YYYY-MM-DD »). */
  period: string;
  amount: string;
  period_amount: string | null;
  covered_after: string | null;
  status: AllocationLineStatus;
}

export interface PaymentPreview {
  membership_id: number;
  contribution_type: { id: number; name: string };
  amount: string;
  currency: string;
  paid_on: string;
  is_free_type: boolean;
  allocations: PaymentAllocationPreviewLine[];
  unallocated_amount: string;
  current: BalanceSummary;
  after: BalanceSummary;
}

export interface PaymentPreviewInput {
  membership_id: number;
  contribution_type_id: number;
  /** Chaîne : jamais de flottant (CLAUDE.md §7 « Montants »). */
  amount: string;
  /** « YYYY-MM-DD ». */
  paid_on: string;
}

export function previewPayment(input: PaymentPreviewInput) {
  return apiPost<PaymentPreview>("/treasury/payments/preview/", input);
}

export interface PaymentAllocation {
  period: string;
  amount: string;
}

export interface Payment {
  id: number;
  membership_id: number;
  contribution_type: { id: number; name: string };
  amount: string;
  currency: string;
  method: PaymentMethod | "card" | "import";
  method_label: string;
  reference: string;
  paid_on: string;
  source: string;
  source_label: string;
  receipt_number: number;
  receipt_available: boolean;
  receipt_url: string;
  attachment_url: string | null;
  validated_at: string | null;
  cash_session_id: string | null;
  client_uuid: string | null;
  client_recorded_at: string | null;
  allocations: PaymentAllocation[];
  player_status: BalanceSummary | null;
}

export interface PaymentCreateInput extends PaymentPreviewInput {
  method: PaymentMethod;
  reference?: string;
  attachment?: File | null;
  /** UUID v4 d'idempotence ; omis s'il est absent, jamais envoyé vide. */
  client_uuid?: string;
}

function toPaymentFormData(input: PaymentCreateInput): FormData {
  const form = new FormData();
  form.append("membership_id", String(input.membership_id));
  form.append("contribution_type_id", String(input.contribution_type_id));
  form.append("amount", input.amount);
  form.append("paid_on", input.paid_on);
  form.append("method", input.method);
  form.append("reference", input.reference ?? "");
  if (input.attachment) form.append("attachment", input.attachment);
  if (input.client_uuid) form.append("client_uuid", input.client_uuid);
  return form;
}

export function createPayment(input: PaymentCreateInput) {
  return apiPost<Payment>("/treasury/payments/", toPaymentFormData(input));
}

// --- Caisse Terrain Express -------------------------------------------------

export type CashSessionState = "open" | "closed" | "expired";

export interface CashSession {
  id: string;
  status: CashSessionState;
  is_open: boolean;
  opened_at: string;
  expires_at: string;
  closed_at: string | null;
  club_timezone: string;
  payments_count: number;
  payments_total: string;
  currency: string;
}

export function getCurrentCashSession() {
  return apiGet<{ session: CashSession | null }>("/treasury/cash-sessions/current/");
}

export function openCashSession() {
  return apiPost<{ session: CashSession }>("/treasury/cash-sessions/", {});
}

export function closeCashSession(id: string) {
  return apiPost<{ session: CashSession }>(`/treasury/cash-sessions/${id}/close/`, {});
}

export interface CashSessionPlayer {
  membership_id: number;
  first_name: string;
  last_name: string;
  jersey_number: number | null;
  photo: string | null;
  membership_status: string;
  membership_status_label: string;
  default_contribution_type_id: number | null;
  balance: string;
  amount_due: string;
  is_in_good_standing: boolean;
  reason: string;
  currency: string;
}

export function searchCashSessionPlayers(sessionId: string, query: string) {
  return apiGet<{ results: CashSessionPlayer[] }>(
    `/treasury/cash-sessions/${sessionId}/players/?q=${encodeURIComponent(query)}`,
  );
}

/** Adapte un résultat de la Caisse Terrain Express au format `PlayerSearch`. */
export function toCashPlayerSearchResult(player: CashSessionPlayer): PlayerSearchResult {
  return {
    id: player.membership_id,
    firstName: player.first_name,
    lastName: player.last_name,
    number: player.jersey_number,
    photoUrl: player.photo,
    status: {
      key: player.is_in_good_standing ? "in_good_standing" : "in_debt",
    },
  };
}

export interface CashPaymentPreviewInput {
  membership_id: number;
  amount: string;
  contribution_type_id?: number | null;
}

export function previewCashPayment(sessionId: string, input: CashPaymentPreviewInput) {
  return apiPost<PaymentPreview>(`/treasury/cash-sessions/${sessionId}/payments/preview/`, input);
}

export interface CashPaymentCreateInput extends CashPaymentPreviewInput {
  client_uuid: string;
  /** ISO 8601 avec fuseau (`new Date().toISOString()`). */
  client_recorded_at: string;
}

export function createCashPayment(sessionId: string, input: CashPaymentCreateInput) {
  return apiPost<Payment>(`/treasury/cash-sessions/${sessionId}/payments/`, input);
}

// ---------------------------------------------------------------------------
// Grille des cotisations (CDC 4.4.7 ; tâche 2.6). Contrats lus dans
// `backend/apps/treasury/{urls,views,serializers}.py`
// (`GridContributionTypesView`, `ContributionGridView`,
// `ContributionGridExportView`, `ContributionGridMonthView`). Aucun état de
// cellule n'est recalculé ici : `state`/`state_label` viennent toujours de
// l'API (CLAUDE.md §2 « Interface »).
// ---------------------------------------------------------------------------

export interface GridContributionType {
  id: number;
  name: string;
  nature: ContributionNature;
  nature_label: string;
  periodicity: ContributionPeriodicity;
  periodicity_label: string;
  amount: string | null;
  scope: ContributionScope;
  status: "active" | "archived";
  is_free: boolean;
}

export interface GridTypesResponse {
  currency: string;
  default_type_id: number | null;
  active: GridContributionType[];
  archived: GridContributionType[];
}

export function getGridContributionTypes() {
  return apiGet<GridTypesResponse>("/treasury/grid/types/");
}

export type GridCellState = "paid" | "partial" | "overdue" | "upcoming" | "free" | "not_due";

export interface GridMonth {
  period: string;
  month: number;
  label: string;
  long_label: string;
}

export interface GridCell {
  period: string;
  month: number;
  amount_due: string | null;
  allocated: string;
  state: GridCellState;
  state_label: string;
  overdue_amount: string;
}

export interface GridRow {
  membership_id: number;
  first_name: string;
  last_name: string;
  name: string;
  jersey_number: number | null;
  photo: string | null;
  membership_status: string;
  membership_status_label: string;
  cells: GridCell[];
  total: string;
  overdue_amount: string;
  has_unpaid: boolean;
  player_status: BalanceSummary | null;
}

export interface GridResponse {
  contribution_type: GridContributionType;
  year: number;
  currency: string;
  today: string;
  months: GridMonth[];
  states: Record<GridCellState, string>;
  rows_total: number;
  count: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  results: GridRow[];
}

export interface GetGridPageParams {
  limit?: number;
  offset?: number;
}

const GRID_PAGE_SIZE = 100;

export function getContributionGridPage(typeId: number, year: number, params: GetGridPageParams = {}) {
  const query = new URLSearchParams({
    limit: String(params.limit ?? GRID_PAGE_SIZE),
    offset: String(params.offset ?? 0),
  });
  return apiGet<GridResponse>(`/treasury/grid/${typeId}/${year}/?${query.toString()}`);
}

/**
 * Enchaîne les pages de l'API (limite serveur : 100 lignes, tâche 2.6) pour
 * renvoyer la grille complète d'un type et d'une année. La pagination
 * affichée à l'écran (50 lignes, CDC 4.4.7) reste ensuite gérée localement
 * par `DataTable` — voir le compte rendu de la tâche 2.8 pour le détail de
 * cette simplification.
 */
export async function getFullContributionGrid(typeId: number, year: number): Promise<GridResponse> {
  const first = await getContributionGridPage(typeId, year, { limit: GRID_PAGE_SIZE, offset: 0 });
  let results = first.results;
  let nextOffset = first.next_offset;
  while (nextOffset !== null) {
    const page = await getContributionGridPage(typeId, year, { limit: GRID_PAGE_SIZE, offset: nextOffset });
    results = results.concat(page.results);
    nextOffset = page.next_offset;
  }
  return { ...first, results, count: results.length };
}

/** Nom de secours seulement : l'API fixe déjà le nom via `Content-Disposition`. */
export function downloadContributionGridCsv(typeId: number, year: number): Promise<DownloadResult> {
  return apiDownload(`/treasury/grid/${typeId}/${year}/export/`, `grille-${year}.csv`);
}

export interface GridMonthPlayer {
  membership_id: number;
  first_name: string;
  last_name: string;
  name: string;
  jersey_number: number | null;
  photo: string | null;
  membership_status: string;
  membership_status_label: string;
}

export interface GridMonthPaymentItem {
  payment_id: number;
  paid_on: string;
  amount: string;
  allocated: string;
  receipt_number: number;
  receipt_url: string;
  method: PaymentMethod | "card" | "import";
  method_label: string;
  source: string;
  source_label: string;
  reference: string;
  spread_from: string;
  spread_to: string;
  spread_label: string | null;
}

export interface GridMonthDetail {
  contribution_type: GridContributionType;
  player: GridMonthPlayer;
  currency: string;
  period: string;
  period_label: string;
  cell: GridCell;
  payments: GridMonthPaymentItem[];
  can_record_payment: boolean;
}

export function getGridMonthDetail(typeId: number, year: number, membershipId: number, month: number) {
  return apiGet<GridMonthDetail>(`/treasury/grid/${typeId}/${year}/members/${membershipId}/months/${month}/`);
}

// ---------------------------------------------------------------------------
// Import des cotisations historiques CSV (CDC 4.4.8 ; tâche 2.6). Contrats
// lus dans `backend/apps/treasury/{urls,views,serializers}.py`
// (`ContributionImportPreviewView`, `ContributionImportView`) et
// `services.preview_contribution_import` / `services.import_contributions`.
// Aucune règle métier ici : la recherche des joueurs, la répartition, les
// montants dus et le solde viennent entièrement du rapport renvoyé par
// l'API (CLAUDE.md §2 « Interface »).
// ---------------------------------------------------------------------------

export interface ContributionImportPaymentLine {
  /** Premier jour du mois concerné (« YYYY-MM-DD »). */
  period: string;
  paid_on: string;
  amount: string;
  /** « amount » : montant du fichier ; « ok » : mois « ok » non couvert par un report. */
  origin: "amount" | "ok";
  reference: string;
}

export interface ContributionImportDueLine {
  period: string;
  amount: string;
  due_date: string;
}

/** « ok » (aperçu, ligne exploitable), « imported » (import définitif), « failed ». */
export type ContributionImportRowStatus = "ok" | "imported" | "failed";

export interface ContributionImportPlayer {
  membership_id: number;
  first_name: string;
  last_name: string;
  name: string;
  jersey_number: number | null;
  photo: string | null;
  membership_status: string;
  membership_status_label: string;
}

export interface ContributionImportRow {
  line_number: number;
  identity: string;
  status: ContributionImportRowStatus;
  player: ContributionImportPlayer | null;
  errors: string[];
  warnings: string[];
  payments: ContributionImportPaymentLine[];
  already_imported: ContributionImportPaymentLine[];
  dues: ContributionImportDueLine[];
  /** Grille résultante pour cette ligne, seulement si non en échec. */
  cells: GridCell[];
  total: string | null;
  balance_before: string | null;
  balance_after: string | null;
  player_status_after: BalanceSummary | null;
}

export interface ContributionImportMonth {
  period: string;
  month: number;
  label: string;
}

export interface ContributionImportSummary {
  rows_total: number;
  rows_succeeded: number;
  rows_failed: number;
  payments_count: number;
  payments_total: string;
  dues_count: number;
  already_imported_count: number;
}

export interface ContributionImportReport {
  is_preview: boolean;
  import_batch_id: number | null;
  contribution_type: GridContributionType;
  year: number;
  currency: string;
  months: ContributionImportMonth[];
  summary: ContributionImportSummary;
  ignored_columns: string[];
  ignored_lines: number[];
  rows: ContributionImportRow[];
}

export interface ContributionImportPreviewInput {
  contribution_type_id: number;
  year: number;
  file: File;
}

function toContributionImportFormData(input: ContributionImportPreviewInput): FormData {
  const form = new FormData();
  form.append("contribution_type_id", String(input.contribution_type_id));
  form.append("year", String(input.year));
  form.append("file", input.file);
  return form;
}

/** Aperçu (CDC 4.4.8) : aucune écriture côté serveur. */
export function previewContributionImport(input: ContributionImportPreviewInput) {
  return apiPost<ContributionImportReport>(
    "/treasury/contribution-imports/preview/",
    toContributionImportFormData(input),
  );
}

/** Import définitif, confirmé par modale de confirmation (CDC 7.2). */
export function createContributionImport(input: ContributionImportPreviewInput) {
  return apiPost<ContributionImportReport>(
    "/treasury/contribution-imports/",
    toContributionImportFormData(input),
  );
}

/**
 * Rapport téléchargeable d'un lot d'import (vue authentifiée
 * `apps.clubs.views.ImportBatchReportDownloadView`, CDC 6.7/7.6). Nom de
 * secours seulement : l'API fixe déjà le nom via `Content-Disposition`.
 */
export function downloadContributionImportReport(importBatchId: number, year: number): Promise<DownloadResult> {
  return apiDownload(`/clubs/imports/${importBatchId}/report/`, `rapport-import-cotisations-${year}.csv`);
}

// ---------------------------------------------------------------------------
// Dépenses (CDC 4.5.1, 4.5.2 ; tâche 2.8). Contrats lus dans
// `backend/apps/treasury/{urls,views,serializers}.py`
// (`ExpenseCategoryListView`, `ExpenseListView`, `ExpenseSummaryView`,
// `ExpenseDetailView`, `ExpenseRefuseView`, `ExpenseReleaseView`,
// `ExpenseDerogationView`, `ExpenseReceiptUploadView`). Aucun état, plafond
// ou délai n'est recalculé ici : tout vient de l'API (CLAUDE.md §2 « Interface »).
// ---------------------------------------------------------------------------

export type ExpenseCategoryStatus = "active" | "archived";

export interface ExpenseCategory {
  id: number;
  name: string;
  ceiling: string | null;
  receipt_required: boolean;
  good_standing_only: boolean;
  status: ExpenseCategoryStatus;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExpenseCategoryInput {
  name?: string;
  ceiling?: string | null;
  receipt_required?: boolean;
  good_standing_only?: boolean;
}

export function getExpenseCategories(status: ExpenseCategoryStatus = "active") {
  return apiGet<ExpenseCategory[]>(`/treasury/expense-categories/?status=${status}`);
}

export function createExpenseCategory(input: ExpenseCategoryInput) {
  return apiPost<ExpenseCategory>("/treasury/expense-categories/", input);
}

export function updateExpenseCategory(id: number, input: ExpenseCategoryInput) {
  return apiPatch<ExpenseCategory>(`/treasury/expense-categories/${id}/`, input);
}

export function archiveExpenseCategory(id: number) {
  return apiPost<ExpenseCategory>(`/treasury/expense-categories/${id}/`, { action: "archive" });
}

export type ExpenseStatus = "pending" | "refused" | "released" | "justified" | "unjustified";

export interface ExpenseAttachment {
  id: number;
  kind: string;
  kind_label: string;
  uploaded_at: string;
  download_url: string;
}

export interface Expense {
  id: number;
  category: { id: number; name: string };
  amount: string;
  currency: string;
  beneficiary_name: string;
  beneficiary_membership_id: number | null;
  reason: string;
  expense_date: string;
  status: ExpenseStatus;
  status_label: string;
  created_by: { id: number; name: string | null };
  created_at: string;
  refused_at: string | null;
  refusal_reason: string;
  released_at: string | null;
  released_by: { id: number; name: string | null } | null;
  justification_deadline: string | null;
  is_overdue: boolean;
  justified_at: string | null;
  unjustified_at: string | null;
  social_assistance_request_id: number | null;
  derogation: { reason: string; granted_at: string; granted_by: string | null } | null;
  attachments: ExpenseAttachment[];
}

export interface ExpenseListResponse {
  count: number;
  next_offset: number | null;
  results: Expense[];
}

export interface GetExpensesParams {
  status?: ExpenseStatus[];
  category?: number;
  limit?: number;
  offset?: number;
}

export function getExpenses(params: GetExpensesParams = {}) {
  const query = new URLSearchParams();
  if (params.status?.length) query.set("status", params.status.join(","));
  if (params.category !== undefined) query.set("category", String(params.category));
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString();
  return apiGet<ExpenseListResponse>(`/treasury/expenses/${suffix ? `?${suffix}` : ""}`);
}

export interface ExpenseSummary {
  can_release: boolean;
  /** Raison en français, déjà formulée par l'API. */
  reason: string;
  blocking_expense_ids: number[];
  available_cash: string;
  currency: string;
}

export function getExpenseSummary() {
  return apiGet<ExpenseSummary>("/treasury/expenses/summary/");
}

export function getExpense(id: number) {
  return apiGet<Expense>(`/treasury/expenses/${id}/`);
}

export interface ExpenseCreateInput {
  category_id: number;
  amount: string;
  beneficiary_name?: string;
  beneficiary_membership_id?: number | null;
  reason: string;
  /** « YYYY-MM-DD ». */
  expense_date: string;
  attachment?: File | null;
}

function toExpenseFormData(input: ExpenseCreateInput): FormData {
  const form = new FormData();
  form.append("category_id", String(input.category_id));
  form.append("amount", input.amount);
  form.append("beneficiary_name", input.beneficiary_name ?? "");
  if (input.beneficiary_membership_id != null) {
    form.append("beneficiary_membership_id", String(input.beneficiary_membership_id));
  }
  form.append("reason", input.reason);
  form.append("expense_date", input.expense_date);
  if (input.attachment) form.append("attachment", input.attachment);
  return form;
}

export function createExpense(input: ExpenseCreateInput) {
  return apiPost<Expense>("/treasury/expenses/", toExpenseFormData(input));
}

export function refuseExpense(id: number, reason: string) {
  return apiPost<Expense>(`/treasury/expenses/${id}/refuse/`, { reason });
}

export function releaseExpense(id: number) {
  return apiPost<Expense>(`/treasury/expenses/${id}/release/`, {});
}

export function releaseExpenseWithDerogation(id: number, reason: string) {
  return apiPost<Expense>(`/treasury/expenses/${id}/release-with-derogation/`, { reason });
}

export function uploadExpenseReceipt(id: number, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiPost<Expense>(`/treasury/expenses/${id}/receipt/`, form);
}

/** Nom de secours seulement : l'API fixe déjà le nom via `Content-Disposition`. */
export function downloadExpenseAttachment(attachmentId: number): Promise<DownloadResult> {
  return apiDownload(`/treasury/expense-attachments/${attachmentId}/`, `depense-${attachmentId}-piece`);
}

// ---------------------------------------------------------------------------
// Assistance sociale (CDC 4.5.3 ; tâche 2.8). Contrats lus dans
// `backend/apps/treasury/{urls,views,serializers}.py`
// (`SocialAssistanceRequestListView`, `SocialAssistanceRequestDetailView`,
// `SocialAssistanceApproveView`, `SocialAssistanceRejectView`). L'éligibilité
// (montant à régulariser, possibilité d'approuver) est calculée uniquement
// par l'API : jamais recalculée ici (10.2 n° 33 et 37).
// ---------------------------------------------------------------------------

export type SocialAssistanceEventType = "birth" | "marriage" | "death";
export type SocialAssistanceRequestStatus = "submitted" | "approved" | "rejected";

export interface SocialAssistanceEligibility {
  eligible: boolean;
  was_in_good_standing_at_event: boolean;
  amount_due_at_event: string;
  amount_to_regularize: string;
  can_be_approved: boolean;
  currency: string;
  /** Raison en français, déjà formulée par l'API. */
  reason: string;
}

export interface SocialAssistanceRequest {
  id: number;
  membership_id: number;
  player_name: string | null;
  event_type: SocialAssistanceEventType;
  event_type_label: string;
  event_date: string;
  description: string;
  planned_amount: string;
  currency: string;
  processing_days: number;
  eligible_at_submission: boolean;
  amount_to_regularize_at_submission: string;
  status: SocialAssistanceRequestStatus;
  status_label: string;
  submitted_at: string;
  decided_at: string | null;
  rejection_reason: string;
  expense: { id: number; status: ExpenseStatus; status_label: string } | null;
  attachment_url: string;
  /** Éligibilité recalculée au moment du traitement (Président, VP ; demandes « Envoyée » seulement). */
  current_eligibility: SocialAssistanceEligibility | null;
}

export interface SocialAssistanceRequestListResponse {
  count: number;
  next_offset: number | null;
  results: SocialAssistanceRequest[];
}

export interface GetSocialAssistanceRequestsParams {
  status?: SocialAssistanceRequestStatus[];
  mine?: boolean;
  limit?: number;
  offset?: number;
}

export function getSocialAssistanceRequests(params: GetSocialAssistanceRequestsParams = {}) {
  const query = new URLSearchParams();
  if (params.status?.length) query.set("status", params.status.join(","));
  if (params.mine) query.set("mine", "1");
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString();
  return apiGet<SocialAssistanceRequestListResponse>(
    `/treasury/social-assistance/requests/${suffix ? `?${suffix}` : ""}`,
  );
}

export function getSocialAssistanceRequest(id: number) {
  return apiGet<SocialAssistanceRequest>(`/treasury/social-assistance/requests/${id}/`);
}

/**
 * Approbation (Président, VP) : elle crée une dépense « En attente » qui suit
 * ensuite le circuit normal de la page Dépenses pour sa libération.
 */
export function approveSocialAssistanceRequest(id: number) {
  return apiPost<SocialAssistanceRequest>(`/treasury/social-assistance/requests/${id}/approve/`, {});
}

export function rejectSocialAssistanceRequest(id: number, reason: string) {
  return apiPost<SocialAssistanceRequest>(`/treasury/social-assistance/requests/${id}/reject/`, { reason });
}

/** Nom de secours seulement : l'API fixe déjà le nom via `Content-Disposition`. */
export function downloadSocialAssistanceAttachment(requestId: number): Promise<DownloadResult> {
  return apiDownload(
    `/treasury/social-assistance/requests/${requestId}/attachment/`,
    `assistance-${requestId}-justificatif`,
  );
}
// ---------------------------------------------------------------------------
// Tableau de bord Trésorerie (CDC 4.4.6), détail d'un paiement, circuit
// d'annulation (CDC 4.4.4) et déclarations « J'ai payé » (CDC 4.6). Contrats
// lus dans `backend/apps/treasury/{urls,views,serializers}.py`
// (`TreasuryDashboardSummaryView`, `PaymentCreateView.get`,
// `PaymentDetailView`, `PaymentReversal*View`, `PaymentDeclaration*View`).
// Aucun indicateur, statut ou solde n'est recalculé ici : tout vient de l'API.
// ---------------------------------------------------------------------------

export interface DashboardSummary {
  /** « YYYY-MM ». */
  period: string;
  currency: string;
  collected: string;
  collection_rate: string;
  matured_due_total: string;
  matured_due_covered: string;
  total_debts: string;
  members_in_debt: number;
  available_cash: string;
}

export function getDashboardSummary(month?: string) {
  const query = month ? `?month=${encodeURIComponent(month)}` : "";
  return apiGet<DashboardSummary>(`/treasury/dashboard/summary/${query}`);
}

export type PaymentStatusKey = "to_validate" | "validated" | "refused" | "cancelled";

export interface PaymentPlayer {
  membership_id: number;
  name: string;
  jersey_number: number | null;
  photo: string | null;
}

export interface PaymentListItem {
  id: number;
  player: PaymentPlayer;
  contribution_type: { id: number; name: string };
  amount: string;
  currency: string;
  paid_on: string;
  method: string;
  method_label: string;
  source: string;
  source_label: string;
  status: PaymentStatusKey;
  status_label: string;
  reversal_pending: boolean;
}

export interface PaymentListResponse {
  count: number;
  next_offset: number | null;
  results: PaymentListItem[];
}

export interface GetPaymentsParams {
  /** Filtre d'état de l'API, ex. « to_validate » (séparés par des virgules). */
  status?: string;
  /** « pending_approval » : paiements dont l'annulation attend le Président. */
  reversal?: "pending_approval";
  /** Paiements d'un seul joueur (modale « Situation financière »). */
  membershipId?: number;
  /** « free » : cotisations libres ; « mandatory » : obligatoires. */
  nature?: ContributionNature;
  limit?: number;
  offset?: number;
}

export function getPayments(params: GetPaymentsParams = {}) {
  const query = new URLSearchParams();
  if (params.membershipId !== undefined) query.set("membership_id", String(params.membershipId));
  if (params.nature) query.set("nature", params.nature);
  if (params.status) query.set("status", params.status);
  if (params.reversal) query.set("reversal", params.reversal);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<PaymentListResponse>(`/treasury/payments/${suffix}`);
}

export interface PaymentActor {
  /** `null` pour « Système Vesta » (Ghost Mode). */
  id: number | null;
  name: string;
}

export type PaymentReversalStatus = "pending_approval" | "approved" | "rejected";

export interface PaymentReversalInfo {
  id: number;
  status: PaymentReversalStatus;
  status_label: string;
  reason: string;
  reason_kind: string;
  requested_by: PaymentActor | null;
  requested_at: string | null;
  approved_by: PaymentActor | null;
  approved_at: string | null;
  rejected_by: PaymentActor | null;
  rejected_at: string | null;
  rejection_reason: string;
}

export type PaymentReversalReasonKind = "error" | "refund";

/** Une demande d'annulation de l'historique (`reversal_history`, la plus récente d'abord). */
export interface PaymentReversalHistoryItem {
  id: number;
  status: PaymentReversalStatus;
  status_label: string;
  reason: string;
  reason_kind: PaymentReversalReasonKind;
  requested_by: PaymentActor;
  requested_at: string;
  decided_by: PaymentActor | null;
  decided_at: string | null;
  rejection_reason: string;
}

export interface PaymentDetail extends Payment {
  player: PaymentPlayer;
  status: PaymentStatusKey;
  status_label: string;
  reversal_pending: boolean;
  submitted_by: PaymentActor | null;
  submitted_at: string | null;
  validated_by: PaymentActor | null;
  rejected_at: string | null;
  rejection_reason: string;
  reversal: PaymentReversalInfo | null;
  reversal_history?: PaymentReversalHistoryItem[];
}

export function getPaymentDetail(id: number) {
  return apiGet<PaymentDetail>(`/treasury/payments/${id}/`);
}

/** Demande d'annulation (Trésorier, adjoint) : motif obligatoire. */
export function requestPaymentReversal(id: number, reason: string) {
  return apiPost<PaymentDetail>(`/treasury/payments/${id}/reversal/`, { reason });
}

/** Validation de l'annulation (Président) : confirmation explicite côté écran. */
export function approvePaymentReversal(id: number) {
  return apiPost<PaymentDetail>(`/treasury/payments/${id}/reversal/approve/`, {});
}

export function rejectPaymentReversal(id: number, rejectionReason: string) {
  return apiPost<PaymentDetail>(`/treasury/payments/${id}/reversal/reject/`, {
    rejection_reason: rejectionReason,
  });
}

export function downloadPaymentReceipt(id: number): Promise<DownloadResult> {
  return apiDownload(`/treasury/payments/${id}/receipt/`, `paiement-${id}-recu.pdf`);
}

export function downloadPaymentAttachment(id: number): Promise<DownloadResult> {
  return apiDownload(`/treasury/payments/${id}/attachment/`, `paiement-${id}-justificatif`);
}

// --- Déclarations « J'ai payé » (CDC 4.6) -----------------------------------

export interface PaymentDeclaration extends Payment {
  status: PaymentStatusKey;
  status_label: string;
  player: { membership_id: number; name: string };
  submitted_at: string | null;
  rejected_at: string | null;
  rejection_reason: string;
  transaction: { provider: string; status: string; external_ref: string };
}

export interface PaymentDeclarationListResponse {
  count: number;
  next_offset: number | null;
  results: PaymentDeclaration[];
}

export interface GetPaymentDeclarationsParams {
  status?: string;
  mine?: boolean;
  limit?: number;
  offset?: number;
}

export function getPaymentDeclarations(params: GetPaymentDeclarationsParams = {}) {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.mine) query.set("mine", "1");
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<PaymentDeclarationListResponse>(`/treasury/payment-declarations/${suffix}`);
}

export function getPaymentDeclaration(id: number) {
  return apiGet<PaymentDeclaration>(`/treasury/payment-declarations/${id}/`);
}

export interface PaymentDeclarationInput {
  contribution_type_id: number;
  /** Chaîne : jamais de flottant. */
  amount: string;
  reference?: string;
  attachment?: File | null;
}

/** « J'ai payé » : le joueur déclare pour lui-même (le serveur déduit le joueur). */
export function createPaymentDeclaration(input: PaymentDeclarationInput) {
  const form = new FormData();
  form.append("contribution_type_id", String(input.contribution_type_id));
  form.append("amount", input.amount);
  form.append("reference", input.reference ?? "");
  if (input.attachment) form.append("attachment", input.attachment);
  return apiPost<PaymentDeclaration>("/treasury/payment-declarations/", form);
}

/** Aperçu de la répartition et du nouveau solde, sans écriture. */
export function previewPaymentDeclaration(id: number) {
  return apiPost<PaymentPreview>(`/treasury/payment-declarations/${id}/preview/`, {});
}

export function validatePaymentDeclaration(id: number) {
  return apiPost<PaymentDeclaration>(`/treasury/payment-declarations/${id}/validate/`, {});
}

export function rejectPaymentDeclaration(id: number, reason: string) {
  return apiPost<PaymentDeclaration>(`/treasury/payment-declarations/${id}/reject/`, { reason });
}

// --- Assistance sociale côté joueur : barèmes, aperçu, envoi (CDC 4.5.3) -----
// Contrats lus dans `SocialAssistanceScaleListView`,
// `SocialAssistancePreviewView` et `SocialAssistanceRequestListView.post`.

export interface SocialAssistanceScale {
  id: number;
  event_type: SocialAssistanceEventType;
  event_type_label: string;
  amount: string;
  processing_days: number;
  expense_category: { id: number; name: string };
  status: string;
  archived_at: string | null;
}

/** Barèmes actifs du club (lecture par tout membre actif). */
export function getSocialAssistanceScales() {
  return apiGet<SocialAssistanceScale[]>("/treasury/social-assistance/scales/");
}

export interface SocialAssistancePreview {
  scale_configured: boolean;
  planned_amount: string | null;
  processing_days: number | null;
  eligibility: SocialAssistanceEligibility;
}

/** Éligibilité, montant prévu et délai, calculés par l'API avant l'envoi. */
export function getSocialAssistancePreview(eventType: SocialAssistanceEventType, eventDate: string) {
  const query = new URLSearchParams({ event_type: eventType, event_date: eventDate });
  return apiGet<SocialAssistancePreview>(`/treasury/social-assistance/preview/?${query.toString()}`);
}

export interface SocialAssistanceRequestInput {
  event_type: SocialAssistanceEventType;
  event_date: string;
  description: string;
  attachment: File;
}

/** Le joueur demande pour lui-même ; le serveur déduit le joueur de la session. */
export function createSocialAssistanceRequest(input: SocialAssistanceRequestInput) {
  const form = new FormData();
  form.append("event_type", input.event_type);
  form.append("event_date", input.event_date);
  form.append("description", input.description);
  form.append("attachment", input.attachment);
  return apiPost<SocialAssistanceRequest>("/treasury/social-assistance/requests/", form);
}

// --- « Mon profil » : mes paiements et mes cotisations (CDC 4.4, 4.6) --------
// (`MyPaymentListView`, `MyPaymentDetailView`, `MyContributionGridView`,
// `MyContributionGridMonthView`). Lecture seule, aucune règle métier ici.

export type MyPaymentStatus = "validated" | "cancelled";

export interface MyPaymentItem {
  id: number;
  contribution_type: { id: number; name: string };
  amount: string;
  currency: string;
  paid_on: string;
  method: string;
  method_label: string;
  source: string;
  source_label: string;
  reference: string;
  status: PaymentStatusKey;
  status_label: string;
  validated_at: string | null;
  receipt_number: number | null;
  receipt_available: boolean;
  receipt_url: string | null;
}

export interface MyPaymentAllocation {
  period: string;
  period_label: string;
  amount: string;
}

export interface MyPaymentDetail extends MyPaymentItem {
  allocations: MyPaymentAllocation[];
}

export interface MyPaymentListResponse {
  count: number;
  next_offset: number | null;
  results: MyPaymentItem[];
}

export interface GetMyPaymentsParams {
  /** Validés par défaut côté API ; « cancelled » pour les paiements annulés. */
  status?: MyPaymentStatus[];
  limit?: number;
  offset?: number;
}

export function getMyPayments(params: GetMyPaymentsParams = {}) {
  const query = new URLSearchParams();
  if (params.status && params.status.length > 0) query.set("status", params.status.join(","));
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<MyPaymentListResponse>(`/treasury/my-payments/${suffix}`);
}

export function getMyPayment(id: number) {
  return apiGet<MyPaymentDetail>(`/treasury/my-payments/${id}/`);
}

export interface MyGridLine {
  contribution_type: GridContributionType;
  cells: GridCell[];
  total: string;
  overdue_amount: string;
  has_unpaid: boolean;
}

export interface MyGridResponse {
  year: number;
  currency: string;
  today: string;
  months: GridMonth[];
  states: Record<GridCellState, string>;
  player_status: BalanceSummary;
  lines: MyGridLine[];
}

export function getMyGrid(year: number) {
  return apiGet<MyGridResponse>(`/treasury/my-grid/${year}/`);
}

export function getMyGridMonthDetail(typeId: number, year: number, month: number) {
  return apiGet<GridMonthDetail>(`/treasury/my-grid/${typeId}/${year}/months/${month}/`);
}

// ---------------------------------------------------------------------------
// Membres du club et « Situation financière » (CDC 4.4.6 ; fiche
// tresorerie-tableau-de-bord §3 point 3, §4.3). Contrats lus dans
// `backend/apps/treasury/{urls,views,serializers}.py` (`MemberListView`,
// `MemberDetailView`, `MemberGridView`). Solde, statuts, impayés et échéances
// sont calculés par l'API : jamais recalculés ici.
// ---------------------------------------------------------------------------

export type MemberStatusKey = "in_good_standing" | "in_debt" | "pending" | "suspended" | "left";

export type MemberOrdering = "balance" | "-balance" | "name" | "-name" | "last_payment" | "-last_payment";

export interface MemberStatusEntry {
  key: MemberStatusKey;
  label: string;
}

export interface MemberRow extends BalanceSummary {
  membership_id: number;
  first_name: string;
  last_name: string;
  name: string;
  jersey_number: number | null;
  photo: string | null;
  membership_status: string;
  membership_status_label: string;
  financial_status: MemberStatusKey;
  financial_status_label: string;
  statuses: MemberStatusEntry[];
  is_suspended: boolean;
  suspension_matches_remaining: number | null;
  monthly_type: { id: number; name: string } | null;
  /** « YYYY-MM-DD » ou `null` si aucun paiement. */
  last_payment_on: string | null;
}

export interface MemberListResponse {
  currency: string;
  today: string;
  ordering: string;
  count: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  results: MemberRow[];
}

export interface GetMembersParams {
  q?: string;
  status?: MemberStatusKey[];
  contributionTypeIds?: number[];
  ordering?: MemberOrdering;
  limit?: number;
  offset?: number;
}

export function getMembers(params: GetMembersParams = {}) {
  const query = new URLSearchParams();
  if (params.q?.trim()) query.set("q", params.q.trim());
  if (params.status?.length) query.set("status", params.status.join(","));
  if (params.contributionTypeIds?.length) query.set("contribution_type", params.contributionTypeIds.join(","));
  if (params.ordering) query.set("ordering", params.ordering);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<MemberListResponse>(`/treasury/members/${suffix}`);
}

export interface MemberTypeRef {
  id: number;
  name: string;
}

export interface MemberNextDue {
  contribution_type: MemberTypeRef | null;
  period: string;
  period_label: string;
  due_date: string;
  amount: string;
}

export interface MemberUnpaidMonth {
  contribution_type: MemberTypeRef | null;
  period: string;
  period_label: string;
  due_date: string;
  amount_due: string;
  allocated: string;
  remaining: string;
}

export interface MemberFreeContribution {
  contribution_type: MemberTypeRef | null;
  total: string;
  payments_count: number;
  last_paid_on: string | null;
}

export interface MemberDetail extends MemberRow {
  today: string;
  next_due: MemberNextDue | null;
  unpaid_months: MemberUnpaidMonth[];
  free_contributions: MemberFreeContribution[];
  can_record_payment: boolean;
}

export function getMemberDetail(membershipId: number) {
  return apiGet<MemberDetail>(`/treasury/members/${membershipId}/`);
}

export interface MemberGridResponse extends MyGridResponse {
  player: GridMonthPlayer;
}

export function getMemberGrid(membershipId: number, year: number) {
  return apiGet<MemberGridResponse>(`/treasury/members/${membershipId}/grid/${year}/`);
}
