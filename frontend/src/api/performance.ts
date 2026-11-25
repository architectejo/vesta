/**
 * Tests de performance du Coach (docs/ecrans/sport-statistiques-seance.md,
 * partie C). Contrats lus dans `backend/apps/sport/{performance,views_performance}.py`.
 * Les décimales sont des chaînes ; toute valeur dérivée (vitesse, taux, rang,
 * progression) vient du serveur : l'interface n'envoie que des valeurs brutes
 * (durée en millisecondes entières, distance et valeur en chaînes décimales).
 */

import { apiGet, apiPatch, apiPost } from "./client";

export type PerformanceKind = "timed_distance" | "distance_in_time" | "repetitions" | "free";
export type PerformanceUnit = "seconds" | "meters" | "kmh" | "repetitions" | "points" | "percent";
export type PerformanceOutcome = "done" | "dnf";
export type PerformanceMethod = "stopwatch" | "manual";
export type PerformanceStartMode = "group" | "individual";
export type LeaderboardPeriod = "last" | "season";

export interface PerformanceTest {
  id: number;
  name: string;
  kind: PerformanceKind;
  kind_label: string;
  kind_text: string;
  distance_m: string | null;
  duration_s: number | null;
  attempts: number | null;
  time_limit_s: number | null;
  unit: PerformanceUnit | "";
  unit_label: string;
  decimals: number;
  higher_is_better: boolean;
  description: string;
  archived: boolean;
  archived_at?: string | null;
  stopwatch_available: boolean;
  has_results: boolean;
}

export interface PerformanceDerived {
  speed_ms?: string;
  speed_kmh?: string;
  speed_display?: string;
  speed_ms_display?: string;
  success_rate?: number;
  success_rate_display?: string;
}

/** Valeur brute d'un résultat et sa mise en forme servie par l'API. */
export interface PerformanceValue {
  outcome: PerformanceOutcome;
  time_ms: number | null;
  distance_m: string | null;
  count: number | null;
  value: string | null;
  display: string;
  derived: PerformanceDerived;
}

export interface PlayerBrief {
  membership_id: number;
  name: string;
  jersey_number: number | null;
  position: string;
  position_label: string;
  photo: string | null;
}

export interface PerformanceTestOverview extends PerformanceTest {
  last_measured_on: string | null;
  last_measured_count: number;
  season_best: ({ player: { membership_id: number; name: string } } & PerformanceValue) | null;
}

export interface PerformanceTemplate {
  code: string;
  name: string;
  kind: PerformanceKind;
  distance_m: string | null;
  duration_s: number | null;
  attempts: number | null;
  time_limit_s: number | null;
  unit: PerformanceUnit | "";
  decimals: number;
  higher_is_better: boolean;
  description: string;
}

export interface PerformanceTemplates {
  results: PerformanceTemplate[];
  health_help: string;
}

export interface PerformanceTestInput {
  name: string;
  kind: PerformanceKind;
  distance_m?: string | null;
  duration_s?: number | null;
  attempts?: number | null;
  time_limit_s?: number | null;
  unit?: PerformanceUnit | "";
  decimals?: number;
  higher_is_better?: boolean;
  description?: string;
}

export function listPerformanceTests(params: { archived?: "only" } = {}) {
  const qs = params.archived ? "?archived=only" : "";
  return apiGet<{ results: PerformanceTestOverview[] }>(`/sport/performance-tests/${qs}`);
}

export function listPerformanceTemplates() {
  return apiGet<PerformanceTemplates>("/sport/performance-test-templates/");
}

export function createPerformanceTest(input: PerformanceTestInput) {
  return apiPost<PerformanceTest>("/sport/performance-tests/", input);
}

export function updatePerformanceTest(id: number, input: Partial<PerformanceTestInput>) {
  return apiPatch<PerformanceTest>(`/sport/performance-tests/${id}/`, input);
}

export function archivePerformanceTest(id: number) {
  return apiPost<PerformanceTest>(`/sport/performance-tests/${id}/archive/`, {});
}

// ---------------------------------------------------------------------------
// Résultats d'une séance
// ---------------------------------------------------------------------------

export interface PerformanceAttempt extends PerformanceValue {
  id: number;
  attempt_no: number;
}

export interface PerformanceResultRow extends PerformanceValue {
  id: number;
  rank: number;
  player: PlayerBrief;
  attempt_no: number;
  attempts_count: number;
  attempts: PerformanceAttempt[];
  method: PerformanceMethod;
  method_label: string;
  personal_record: boolean;
  recorded_by: { id: number | null; name: string };
  recorded_at: string;
}

export interface PerformanceDnfRow extends PerformanceValue {
  id: number;
  player: PlayerBrief;
  attempt_no: number;
  method: PerformanceMethod;
}

export interface EventPerformanceResults {
  event_id: number;
  date: string;
  test: PerformanceTest;
  scope: "all" | "mine";
  summary: { measured_count: number; best: string | null; average: string | null };
  results: PerformanceResultRow[];
  dnf: PerformanceDnfRow[];
  window_open: boolean;
  my_best_overall?: ({ date: string } & PerformanceValue) | null;
}

export function getEventPerformanceResults(eventId: number, testId: number) {
  return apiGet<EventPerformanceResults>(`/sport/events/${eventId}/performance-results/?test=${testId}`);
}

// ---------------------------------------------------------------------------
// Envoi groupé des mesures
// ---------------------------------------------------------------------------

export interface BulkPerformanceItem {
  membership_id: number;
  attempt_no?: number;
  /** Durée en millisecondes ENTIÈRES (jamais de flottant côté client). */
  time_ms?: number;
  distance_m?: string;
  count?: number;
  value?: string;
  outcome?: PerformanceOutcome;
  client_uuid?: string;
}

export interface BulkPerformanceInput {
  test_id: number;
  method: PerformanceMethod;
  start_mode?: PerformanceStartMode | "";
  client_uuid: string;
  items: BulkPerformanceItem[];
}

export interface BulkPerformanceItemResult {
  membership_id: number;
  outcome: "created" | "skipped" | "refused";
  message: string;
  warning: string;
  result: ({ id: number; attempt_no: number } & PerformanceValue) | null;
}

export interface BulkPerformanceResponse {
  run_id: number | null;
  counts: { created: number; skipped: number; refused: number };
  results: BulkPerformanceItemResult[];
}

export function bulkPerformanceResults(eventId: number, input: BulkPerformanceInput) {
  return apiPost<BulkPerformanceResponse>(`/sport/events/${eventId}/performance-results/bulk/`, input);
}

// ---------------------------------------------------------------------------
// Détail, correction, retrait
// ---------------------------------------------------------------------------

export interface PerformanceCorrection {
  id: number;
  actor: { id: number | null; name: string };
  created_at: string;
  reason: string;
  before: PerformanceValue & { status: string };
  after: PerformanceValue & { status: string };
}

export interface PerformanceResultDetail extends PerformanceValue {
  id: number;
  event_id: number;
  date: string;
  test: PerformanceTest;
  player: PlayerBrief;
  attempt_no: number;
  method: PerformanceMethod;
  method_label: string;
  status: "active" | "voided";
  recorded_by: { id: number | null; name: string };
  recorded_at: string;
  locked: boolean;
  corrections: PerformanceCorrection[];
}

export interface PerformanceCorrectionInput {
  reason: string;
  outcome?: PerformanceOutcome;
  time_ms?: number;
  distance_m?: string;
  count?: number;
  value?: string;
}

export function getPerformanceResult(id: number) {
  return apiGet<PerformanceResultDetail>(`/sport/performance-results/${id}/`);
}

export function correctPerformanceResult(id: number, input: PerformanceCorrectionInput) {
  return apiPatch<PerformanceResultDetail>(`/sport/performance-results/${id}/`, input);
}

export function voidPerformanceResult(id: number, reason: string) {
  return apiPost<PerformanceResultDetail>(`/sport/performance-results/${id}/void/`, { reason });
}

// ---------------------------------------------------------------------------
// Classement, évolution, « mes mesures »
// ---------------------------------------------------------------------------

export interface PerformanceTrend {
  direction: "progress" | "regress" | "stable";
  delta: string;
  delta_display: string;
  text: string;
}

export interface LeaderboardRow extends PerformanceValue {
  rank: number;
  player: PlayerBrief;
  result_id: number;
  event_id: number;
  date: string;
  measures_count: number;
  trend: PerformanceTrend | null;
  personal_record: boolean;
}

export interface PerformanceLeaderboard {
  test: PerformanceTest;
  period: LeaderboardPeriod;
  event: { id: number; date: string } | null;
  results: LeaderboardRow[];
}

export function getPerformanceLeaderboard(testId: number, period: LeaderboardPeriod) {
  return apiGet<PerformanceLeaderboard>(`/sport/performance-tests/${testId}/leaderboard/?period=${period}`);
}

export interface PerformanceEvolutionPoint extends PerformanceValue {
  event_id: number;
  date: string;
  result_id: number;
  sort_value: string;
}

export interface PerformanceEvolution {
  membership: PlayerBrief;
  test: PerformanceTest;
  best: ({ date: string; result_id: number } & PerformanceValue) | null;
  last: ({ date: string; result_id: number } & PerformanceValue) | null;
  progression: (PerformanceTrend & { legend: string }) | null;
  points: PerformanceEvolutionPoint[];
  results: Array<
    PerformanceValue & {
      id: number;
      event_id: number;
      date: string;
      attempt_no: number;
      method: PerformanceMethod;
      method_label: string;
      personal_record: boolean;
    }
  >;
}

export interface PerformanceOverview {
  membership: PlayerBrief;
  tests: Array<{
    test: PerformanceTest;
    best: { date: string } & PerformanceValue;
    last: { date: string } & PerformanceValue;
    results_count: number;
  }>;
}

export function getPlayerPerformanceOverview(membershipId: number) {
  return apiGet<PerformanceOverview>(`/sport/players/${membershipId}/performance/`);
}

export function getPlayerPerformanceEvolution(membershipId: number, testId: number) {
  return apiGet<PerformanceEvolution>(`/sport/players/${membershipId}/performance/?test=${testId}`);
}

export function getMyPerformanceOverview() {
  return apiGet<PerformanceOverview>("/sport/performance/me/");
}

export function getMyPerformanceEvolution(testId: number) {
  return apiGet<PerformanceEvolution>(`/sport/performance/me/?test=${testId}`);
}
