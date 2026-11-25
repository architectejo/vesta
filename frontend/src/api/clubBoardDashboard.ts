/**
 * Tableau de bord du Président et du Vice-président (fiche
 * `docs/ecrans/club-tableau-de-bord-bureau.md` §4, §5, §10). Contrats lus dans
 * `backend/apps/clubs/board_dashboard.py` et `backend/apps/treasury/dashboard.py`.
 * L'interface n'y calcule rien : taux et montants sont des chaînes de l'API
 * (taux « 74.00 » ou null ; montants à 2 décimales dans `currency`).
 */

import { apiGet } from "./client";

// ---------------------------------------------------------------------------
// Communs
// ---------------------------------------------------------------------------

export type Rate = string | null;
export type Money = string;

export interface CardError {
  error: string;
}

/** Une carte vaut ses données ou `{ error }` sans faire échouer les autres. */
export type Card<T> = T | CardError;

export function isCardError<T extends object>(card: Card<T> | undefined): card is CardError {
  return card !== undefined && typeof card === "object" && card !== null && "error" in card;
}

export interface BoardPeriod {
  mode: "month" | "season";
  month: string | null;
  season_id: number | null;
  label: string;
  start: string;
  end: string;
  months: string[];
}

/** Période demandée : mois « AAAA-MM », saison par identifiant, ou saison courante. */
export type BoardPeriodQuery =
  | { mode: "month"; month: string }
  | { mode: "season"; seasonId: string | null };

export interface PagedList<T> {
  items: T[];
  count: number;
  next_offset: number | null;
}

export interface PlayerRef {
  membership_id: number | null;
  player_name: string | null;
  photo: string | null;
}

// ---------------------------------------------------------------------------
// Cartes
// ---------------------------------------------------------------------------

export interface AttendancePoint {
  event_id: number;
  kind: string;
  kind_label: string;
  date: string;
  expected: number;
  present: number;
  late: number;
  excused: number;
  absent: number;
  rate: Rate;
}

export interface AttendanceCard {
  events_count: number;
  average_rate: Rate;
  last_rate: Rate;
  late_counts_absent: boolean;
  totals: { expected: number; present: number; late: number; excused: number; absent: number };
  by_kind: Record<string, { events: number; average_rate: Rate }>;
  points: AttendancePoint[];
  series: Array<{ month: string; label: string; events: number; rate: Rate }>;
}

export interface ContributionsSeriesPoint {
  month: string;
  label: string;
  collected: Money;
  matured_due_total: Money;
  matured_due_covered: Money;
  collection_rate: Rate;
}

export interface ContributionsCard {
  collected: Money;
  collected_mandatory: Money;
  collected_free: Money;
  due_total: Money;
  matured_due_total: Money;
  matured_due_covered: Money;
  collection_rate: Rate;
  series: ContributionsSeriesPoint[];
}

export interface SquadStatusCard {
  as_of: string;
  total: number;
  in_good_standing: { count: number; rate: Rate };
  in_debt: { count: number; rate: Rate; amount: Money };
  pending: { count: number; rate: Rate };
  suspended: { count: number; rate: Rate; also_in_debt_count: number; also_in_debt_amount: Money };
}

export interface CashSeriesPoint {
  month: string;
  label: string;
  collected: Money;
  spent: Money;
}

export interface CashCard {
  collected: Money;
  spent: Money;
  net: Money;
  available_cash: Money;
  series: CashSeriesPoint[];
}

export interface ExpenseCategory {
  category_id: number | null;
  name: string;
  amount: Money;
  count: number;
}

export interface ExpensesByCategoryCard {
  total_spent: Money;
  categories: ExpenseCategory[];
  pending_count: number;
  pending_amount: Money;
  unjustified_count: number;
  release_blocked: boolean;
  release_blocked_reason: string | null;
}

export type UpcomingItemKind =
  | "session"
  | "match"
  | "assembly"
  | "licence"
  | "contribution_due"
  | "expense_justification";

export interface UpcomingItem {
  kind: UpcomingItemKind;
  date: string;
  time?: string | null;
  label: string;
  detail?: string;
  debt_on?: string;
  players_count?: number;
  amount?: Money;
}

export interface UpcomingFinanceCard {
  as_of: string;
  until: string;
  count: number;
  items: UpcomingItem[];
}

export interface UpcomingCard {
  as_of: string;
  until: string;
  count: number;
  items: UpcomingItem[];
}

export interface NewcomersCard {
  arrivals_count: number;
  departures_count: number;
  avatars: PlayerRef[];
  pending_count: number;
  series: Array<{ month: string; label: string; arrivals: number; departures: number }>;
}

export interface MatchSummary {
  match_id: number;
  date: string;
  opponent: string;
  venue: string;
  venue_label: string;
  match_type: string;
  match_type_label: string;
  goals_for: number;
  goals_against: number;
  result: "V" | "N" | "D";
  result_label: string;
}

export interface ResultsCard {
  played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_for: number;
  goals_against: number;
  form: MatchSummary[];
}

export interface DisciplineCard {
  yellow_cards: number;
  red_cards: number;
  internal_sanctions: number;
  suspended_count: number;
  series: Array<{ month: string; label: string; yellow: number; red: number; internal: number }>;
}

export interface SquadTrendCard {
  current_count: number;
  window_start: string;
  window_end: string;
  arrivals_count: number;
  departures_count: number;
  series: Array<{ month: string; label: string; count: number; arrivals: number; departures: number }>;
}

export interface FitnessPlayer extends PlayerRef {
  fitness_status: "fit" | "fit_with_restriction" | "unfit";
  return_date: string | null;
}

/** Aptitude seulement : aucun diagnostic n'existe dans ce contrat (règle 11). */
export interface FitnessCard {
  total: number;
  fit: number;
  fit_with_restriction: number;
  unfit: number;
  recorded_count: number;
  no_information: boolean;
  unfit_players: FitnessPlayer[];
  notice: string;
}

export interface PlayerAttendanceRow extends PlayerRef {
  expected: number;
  present: number;
  late: number;
  excused: number;
  absent: number;
  rate: Rate;
}

export interface AttendanceRankingCard {
  players_count: number;
  top: PlayerAttendanceRow[];
  bottom: PlayerAttendanceRow[];
}

export interface ToProcessCard {
  counts: {
    expenses_to_validate: number;
    assistance_requests: number;
    minutes_to_sign: number;
    blocked_applications: number;
  };
  total: number;
}

export interface EquipmentLoan extends PlayerRef {
  article_id: number;
  article_name: string;
  quantity: number;
  since: string;
  match_id: number | null;
  players_count: number;
  overdue_days: number;
  is_overdue: boolean;
}

export interface EquipmentOutCard {
  lines_count: number;
  articles_count: number;
  overdue_count: number;
  items: EquipmentLoan[];
}

export interface CoachNotesEvent {
  event_id: number;
  kind: string;
  kind_label: string;
  date: string;
  average: Rate;
  evaluations: number;
}

export interface CoachNotesCard {
  average: Rate;
  evaluations: number;
  events_count: number;
  points: CoachNotesEvent[];
  series: Array<{ month: string; label: string; average: Rate }>;
}

export interface FeedActivityCard {
  posts_count: number;
  comments_count: number;
  likes_count: number;
  granularity: "week" | "month";
  series: Array<{ start: string; label: string; posts: number }>;
}

export interface BoardDashboard {
  period: BoardPeriod;
  currency: string;
  as_of: string;
  attendance: Card<AttendanceCard>;
  contributions: Card<ContributionsCard>;
  squad_status: Card<SquadStatusCard>;
  cash: Card<CashCard>;
  expenses_by_category: Card<ExpensesByCategoryCard>;
  upcoming_finance: Card<UpcomingFinanceCard>;
  newcomers: Card<NewcomersCard>;
  results: Card<ResultsCard>;
  discipline: Card<DisciplineCard>;
  squad_trend: Card<SquadTrendCard>;
  fitness: Card<FitnessCard>;
  upcoming: Card<UpcomingCard>;
  attendance_ranking: Card<AttendanceRankingCard>;
  to_process: Card<ToProcessCard>;
  equipment_out: Card<EquipmentOutCard>;
  coach_notes: Card<CoachNotesCard>;
  feed_activity: Card<FeedActivityCard>;
}

export type BoardCardKey =
  | "attendance"
  | "contributions"
  | "squad_status"
  | "cash"
  | "expenses_by_category"
  | "upcoming_finance"
  | "newcomers"
  | "results"
  | "discipline"
  | "squad_trend"
  | "fitness"
  | "upcoming"
  | "attendance_ranking"
  | "to_process"
  | "equipment_out"
  | "coach_notes"
  | "feed_activity";

// ---------------------------------------------------------------------------
// Détails (modales)
// ---------------------------------------------------------------------------

export interface ArrivalItem extends PlayerRef {
  position: string;
  position_label: string;
  joined_on: string;
  sponsor_name: string | null;
}

export interface PendingItem extends ArrivalItem {
  stage: string;
  stage_label: string;
  missing_steps: Array<{ code: string; label: string }>;
}

export interface DepartureItem extends PlayerRef {
  left_on: string | null;
  left_reason: string;
  left_reason_label: string;
}

export interface SuspensionItem extends PlayerRef {
  reason: string;
  reason_label: string;
  matches_total?: number;
  matches_served?: number;
  matches_remaining: number;
  since?: string;
  also_in_debt?: boolean;
  amount_due?: Money | null;
}

export interface IncidentItem extends PlayerRef {
  incident_id: number;
  date: string;
  type: string;
  type_label: string;
  cause: string;
  cause_label: string;
  cause_detail: string;
  minute: number | null;
}

export interface RankedPlayer extends PlayerRef {
  count: number;
}

export interface SanctionedPlayer extends PlayerRef {
  yellow: number;
  red: number;
  internal: number;
  total: number;
}

export interface ToProcessItem extends Partial<PlayerRef> {
  kind: "expense_to_validate" | "assistance_request" | "minutes_to_sign" | "blocked_application";
  date: string | null;
  label: string;
  amount?: Money;
  ref_id: number;
}

export interface FeedPostItem {
  post_id: number;
  date: string;
  kind: string;
  kind_label: string;
  author_name: string;
  excerpt: string;
  likes_count: number;
  comments_count: number;
}

export interface PaymentItem {
  payment_id: number;
  paid_on: string;
  membership_id: number;
  player_name: string;
  photo?: string | null;
  contribution_type_id: number;
  contribution_type_name: string;
  nature: "mandatory" | "free";
  amount: Money;
  status: "validated" | "cancelled";
  status_label: string;
}

export interface DebtorItem extends PlayerRef {
  amount_due: Money;
}

export interface SquadPlayerItem extends PlayerRef {
  amount_due?: Money;
  is_suspended?: boolean;
}

export interface ContributionTypeRow {
  contribution_type_id: number;
  name: string;
  nature: "mandatory" | "free";
  nature_label: string;
  collected: Money;
  due_total: Money | null;
  matured_due_total: Money | null;
  matured_due_covered: Money | null;
  collection_rate: Rate;
}

export interface CashMonthRow {
  month: string;
  label: string;
  collected: Money;
  spent: Money;
  net: Money;
  cash_end: Money;
}

export interface ExpenseItem {
  expense_id: number;
  expense_date: string;
  category_id: number | null;
  category_name: string;
  amount: Money;
  beneficiary_name: string;
  status: "pending" | "released" | "justified" | "unjustified";
  status_label: string;
  justification_deadline: string | null;
  is_overdue: boolean;
}

interface SectionBase {
  section: string;
  period: BoardPeriod;
}

export interface AttendanceDetail extends SectionBase {
  summary: AttendanceCard;
  sessions: PagedList<AttendancePoint>;
}
export interface AttendanceRankingDetail extends SectionBase {
  summary: AttendanceRankingCard;
  players: PagedList<PlayerAttendanceRow>;
}
export interface NewcomersDetail extends SectionBase {
  summary: NewcomersCard;
  arrivals: PagedList<ArrivalItem>;
  pending: PagedList<PendingItem>;
  departures: PagedList<DepartureItem>;
}
export interface SquadTrendDetail extends SectionBase {
  summary: SquadTrendCard;
  arrivals: PagedList<ArrivalItem>;
  departures: PagedList<DepartureItem>;
}
export interface ResultsDetail extends SectionBase {
  summary: ResultsCard;
  top_scorers: RankedPlayer[];
  top_assists: RankedPlayer[];
  matches: PagedList<MatchSummary>;
}
export interface DisciplineDetail extends SectionBase {
  summary: DisciplineCard;
  most_sanctioned: SanctionedPlayer[];
  suspensions: PagedList<SuspensionItem>;
  incidents: PagedList<IncidentItem>;
}
export interface FitnessDetail extends SectionBase {
  summary: FitnessCard;
  unfit: PagedList<FitnessPlayer>;
  restricted: PagedList<FitnessPlayer>;
  fit: PagedList<FitnessPlayer>;
}
export interface UpcomingDetail extends SectionBase {
  summary: UpcomingCard;
  items: PagedList<UpcomingItem>;
}
export interface UpcomingFinanceDetail extends SectionBase {
  currency: string;
  upcoming: PagedList<UpcomingItem> & { as_of: string; until: string };
}
export interface ToProcessDetail extends SectionBase {
  summary: ToProcessCard;
  items: PagedList<ToProcessItem>;
}
export interface EquipmentOutDetail extends SectionBase {
  summary: EquipmentOutCard;
  loans: PagedList<EquipmentLoan>;
}
export interface CoachNotesDetail extends SectionBase {
  summary: CoachNotesCard;
  events: PagedList<CoachNotesEvent>;
}
export interface FeedActivityDetail extends SectionBase {
  summary: FeedActivityCard;
  posts: PagedList<FeedPostItem>;
}
export interface ContributionsDetail extends SectionBase {
  currency: string;
  summary: Omit<ContributionsCard, "series">;
  series: ContributionsSeriesPoint[];
  by_type: ContributionTypeRow[];
  payments: PagedList<PaymentItem>;
  debtors: PagedList<DebtorItem> & { as_of: string };
}
export interface SquadStatusDetail extends SectionBase {
  currency: string;
  summary: SquadStatusCard;
  in_good_standing: PagedList<SquadPlayerItem>;
  in_debt: PagedList<SquadPlayerItem>;
  pending: PagedList<SquadPlayerItem>;
  suspended: PagedList<SuspensionItem>;
}
export interface CashDetail extends SectionBase {
  currency: string;
  summary: Omit<CashCard, "series">;
  opening_cash: Money;
  months: CashMonthRow[];
}
export interface ExpensesDetail extends SectionBase {
  currency: string;
  summary: Omit<ExpensesByCategoryCard, "categories">;
  categories: ExpenseCategory[];
  expenses: PagedList<ExpenseItem>;
}

export interface BoardSectionDetails {
  attendance: AttendanceDetail;
  attendance_ranking: AttendanceRankingDetail;
  newcomers: NewcomersDetail;
  squad_trend: SquadTrendDetail;
  results: ResultsDetail;
  discipline: DisciplineDetail;
  fitness: FitnessDetail;
  upcoming: UpcomingDetail;
  upcoming_finance: UpcomingFinanceDetail;
  to_process: ToProcessDetail;
  equipment_out: EquipmentOutDetail;
  coach_notes: CoachNotesDetail;
  feed_activity: FeedActivityDetail;
  contributions: ContributionsDetail;
  squad_status: SquadStatusDetail;
  cash: CashDetail;
  expenses_by_category: ExpensesDetail;
}

export type BoardSectionKey = keyof BoardSectionDetails;

// ---------------------------------------------------------------------------
// Appels
// ---------------------------------------------------------------------------

/** Paramètres de période du contrat : rien = mois courant, saison sans id = saison courante. */
export function periodSearchParams(period: BoardPeriodQuery | null): URLSearchParams {
  const params = new URLSearchParams();
  if (!period) return params;
  if (period.mode === "month") {
    params.set("period", "month");
    params.set("month", period.month);
  } else {
    params.set("period", "season");
    if (period.seasonId) params.set("season", period.seasonId);
  }
  return params;
}

export function getBoardDashboard(period: BoardPeriodQuery | null) {
  const qs = periodSearchParams(period).toString();
  return apiGet<BoardDashboard>(`/clubs/board-dashboard/${qs ? `?${qs}` : ""}`);
}

export interface BoardSectionOptions {
  limit?: number;
  offset?: number;
  /** Nom de la liste à recharger (« Voir plus »). */
  only?: string;
}

export function getBoardSection<K extends BoardSectionKey>(
  section: K,
  period: BoardPeriodQuery | null,
  options: BoardSectionOptions = {},
) {
  const params = periodSearchParams(period);
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  if (options.only) params.set("only", options.only);
  return apiGet<BoardSectionDetails[K]>(`/clubs/board-dashboard/${section}/?${params.toString()}`);
}
