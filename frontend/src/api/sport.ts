/**
 * Appels de l'app `sport` (tâche 3.7, lot 3). Contrats lus directement dans
 * `backend/apps/sport/{urls,views,serializers}.py` (vérifiés indépendamment,
 * 108 tests) : aucune forme n'est devinée ici.
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

// ---------------------------------------------------------------------------
// Types communs
// ---------------------------------------------------------------------------

export interface MembershipBrief {
  membership_id: number;
  name: string;
  jersey_number: number | null;
  position: string;
  position_label: string;
  photo: string | null;
}

export interface ReasonInfo {
  eligible: boolean;
  reason_code: string;
  reason: string;
}

export interface ActorBrief {
  id: number | null;
  name: string;
}

export interface EventCommon {
  id: number;
  kind: "session" | "match";
  event_date: string;
  season_id: number | null;
  is_locked: boolean;
  unlocked_by: ActorBrief | null;
  unlocked_at: string | null;
  unlock_reason: string;
}

export type AttendanceStatus = "present" | "late_absent" | "absent" | "excused_absent";

/** Droits de pointage groupé renvoyés par l'API (faux si l'événement est verrouillé). */
export interface AttendanceCapabilities {
  can_bulk_mark: boolean;
  can_bulk_excuse: boolean;
  can_set_arrival_time: boolean;
}

export interface Attendance {
  id: number;
  membership_id: number;
  player: MembershipBrief;
  status: AttendanceStatus;
  status_label: string;
  arrived_at: string | null;
  excused_reason: string;
  marked_by: ActorBrief | null;
  client_uuid: string | null;
}

export interface TeamAssignmentItem {
  id: number;
  membership_id: number;
  player: MembershipBrief;
  team: "A" | "B";
  arrival_order: number;
  /** Sur le terrain (max. 11 par équipe) ou sur le banc — extension
   * client du 30/09/2026 (hors CDC écrit à ce jour, voir
   * `apps.sport.services.place_team_player`). */
  is_on_field: boolean;
  x_coord: string | null;
  y_coord: string | null;
}

export interface UnassignedGroups {
  to_place_manually: Array<MembershipBrief & { attendance_status: AttendanceStatus }>;
  cannot_play: Array<MembershipBrief & ReasonInfo>;
}

export interface AttendanceCounts {
  present: number;
  late: number;
  excused: number;
  not_marked: number;
}

// ---------------------------------------------------------------------------
// Séances (CDC 4.7)
// ---------------------------------------------------------------------------

export interface SessionListItem {
  id: number;
  event_date: string;
  gathering_time: string;
  late_arrival_cutoff: string;
  location: string;
  is_locked: boolean;
}

export interface SessionDetail extends EventCommon {
  gathering_time: string;
  late_arrival_cutoff: string;
  location: string;
  team_a_color: string;
  team_b_color: string;
  /** Formation choisie pour chaque équipe, indépendamment l'une de
   * l'autre — extension client du 30/09/2026 (hors CDC écrit à ce jour,
   * voir `apps.sport.services.set_team_formation`). Chaîne vide tant
   * qu'aucune formation n'a été choisie. */
  team_a_formation: Formation | "";
  team_b_formation: Formation | "";
  instructions: string;
  late_arrival_counts_absent: boolean;
  counts: AttendanceCounts;
  attendances: Attendance[];
  team_a: TeamAssignmentItem[];
  team_b: TeamAssignmentItem[];
  unassigned: UnassignedGroups;
  capabilities?: AttendanceCapabilities;
}

export interface SessionInput {
  season_id?: number | null;
  event_date: string;
  gathering_time: string;
  late_arrival_cutoff: string;
  location?: string;
  team_a_color?: string | null;
  team_b_color?: string | null;
  instructions?: string;
}

export function listSessions(params: { limit?: number; offset?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<{ count: number; next_offset: number | null; results: SessionListItem[] }>(
    `/sport/sessions/${suffix}`,
  );
}

export function createSession(input: SessionInput) {
  return apiPost<SessionDetail>("/sport/sessions/", input);
}

export function getSession(id: number) {
  return apiGet<SessionDetail>(`/sport/sessions/${id}/`);
}

export function updateSession(id: number, input: SessionInput) {
  return apiPatch<SessionDetail>(`/sport/sessions/${id}/`, input);
}

export function getSessionUnassigned(id: number) {
  return apiGet<UnassignedGroups>(`/sport/sessions/${id}/unassigned/`);
}

export interface AttendanceMarkInput {
  membership_id: number;
  arrived_at?: string;
  client_uuid?: string;
  client_recorded_at?: string;
}

export function markSessionAttendance(sessionId: number, input: AttendanceMarkInput) {
  return apiPost<Attendance>(`/sport/sessions/${sessionId}/attendance/`, input);
}

export function excuseSessionAttendance(sessionId: number, input: { membership_id: number; reason: string }) {
  return apiPost<Attendance>(`/sport/sessions/${sessionId}/attendance/excuse/`, input);
}

export function correctAttendanceTime(attendanceId: number, arrivedAt: string) {
  return apiPatch<Attendance>(`/sport/attendance/${attendanceId}/`, { arrived_at: arrivedAt });
}

export function assignTeam(sessionId: number, input: { membership_id: number; team: "A" | "B" }) {
  return apiPost<TeamAssignmentItem>(`/sport/sessions/${sessionId}/team-assignment/`, input);
}

/** Choisit la formation d'une équipe de séance, indépendamment de
 * l'autre équipe (extension client du 30/09/2026, hors CDC écrit à ce
 * jour -- voir `apps.sport.services.set_team_formation`). Renvoie la
 * séance complète à jour (même forme que `getSession`). */
export function setTeamFormation(sessionId: number, input: { team: "A" | "B"; formation: Formation }) {
  return apiPost<SessionDetail>(`/sport/sessions/${sessionId}/team-formation/`, input);
}

/** Place, déplace (avec échange automatique si la case est occupée par
 * un coéquipier) ou renvoie au banc un joueur déjà réparti en équipe A/B
 * (extension client du 30/09/2026, hors CDC écrit à ce jour -- voir
 * `apps.sport.services.place_team_player`). `x_coord`/`y_coord` tous
 * deux `null` renvoie le joueur au banc. Renvoie la séance complète à
 * jour (même forme que `getSession`). */
export function placeTeamPlayer(
  sessionId: number,
  input: { team: "A" | "B"; membership_id: number; x_coord: number | null; y_coord: number | null },
) {
  return apiPost<SessionDetail>(`/sport/sessions/${sessionId}/team-placement/`, input);
}

// ---------------------------------------------------------------------------
// Événements communs (verrouillage, incidents, évaluations)
// ---------------------------------------------------------------------------

export function unlockEvent(eventId: number, reason: string) {
  return apiPost<EventCommon>(`/sport/events/${eventId}/unlock/`, { reason });
}

export type IncidentType = "yellow_card" | "red_card" | "internal_sanction";
export type IncidentCause = "contestation" | "serious_foul" | "behaviour" | "lateness" | "other";

export interface Incident {
  id: number;
  event_id: number;
  player: MembershipBrief;
  incident_type: IncidentType;
  incident_type_label: string;
  cause: IncidentCause;
  cause_label: string;
  cause_detail: string;
  issued_by: string;
  minute: number | null;
  recorded_by: ActorBrief | null;
  recorded_at: string;
}

export interface IncidentInput {
  membership_id: number;
  incident_type: IncidentType;
  cause: IncidentCause;
  cause_detail?: string;
  issued_by?: string;
  minute?: number | null;
}

export function listEventIncidents(eventId: number, params: { limit?: number; offset?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<{ count: number; next_offset: number | null; results: Incident[] }>(
    `/sport/events/${eventId}/incidents/${suffix}`,
  );
}

export function createIncident(eventId: number, input: IncidentInput) {
  return apiPost<Incident>(`/sport/events/${eventId}/incidents/`, input);
}

export interface Suspension {
  id: number;
  membership_id: number;
  reason: string;
  reason_label: string;
  matches_total: number;
  matches_served: number;
  matches_remaining: number;
  is_active: boolean;
  lifted_at: string | null;
  created_at: string;
}

export function listSuspensions(params: { membershipId?: number; active?: boolean } = {}) {
  const qs = new URLSearchParams();
  if (params.membershipId) qs.set("membership_id", String(params.membershipId));
  if (params.active) qs.set("active", "1");
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<{ count: number; next_offset: number | null; results: Suspension[] }>(
    `/sport/suspensions/${suffix}`,
  );
}

export interface Evaluation {
  id: number;
  membership_id: number;
  player: MembershipBrief;
  evaluator_id: number;
  overall_score: string;
  technical_score: string | null;
  physical_score: string | null;
  tactical_score: string | null;
  mental_score: string | null;
  attitude_score: string | null;
  comment: string;
  comment_visible_to_player: boolean;
  created_at: string;
}

export interface EvaluationInput {
  membership_id: number;
  overall_score: string;
  technical_score?: string | null;
  physical_score?: string | null;
  tactical_score?: string | null;
  mental_score?: string | null;
  attitude_score?: string | null;
  comment?: string;
  comment_visible_to_player?: boolean;
}

export function listEventEvaluations(eventId: number, membershipId?: number) {
  const qs = membershipId ? `?membership_id=${membershipId}` : "";
  return apiGet<{ results: Evaluation[]; averages: Record<string, string>; is_locked: boolean; locks_at: string }>(
    `/sport/events/${eventId}/evaluations/${qs}`,
  );
}

export function createEvaluation(eventId: number, input: EvaluationInput) {
  return apiPost<Evaluation>(`/sport/events/${eventId}/evaluations/`, input);
}

// ---------------------------------------------------------------------------
// Statistiques de séance (docs/ecrans/sport-statistiques-seance.md, parties A et B)
// Contrats lus dans `backend/apps/sport/session_stats.py`. Décimales en
// chaînes ; tout calcul et tout filtrage par rôle viennent de l'API.
// ---------------------------------------------------------------------------

export type StatsPeriod = "last10" | "season";

export interface AttendanceStatsLate extends MembershipBrief {
  arrived_at: string | null;
}

export interface AttendanceStatsExcused extends MembershipBrief {
  reason: string;
}

export interface SessionAttendanceStats {
  expected: number;
  present: number;
  late: number;
  absent: number;
  excused: number;
  /** `null` : séance sans aucun pointage (jamais affiché « 0 % »). */
  rate: number | null;
  nobody_marked: boolean;
  late_counts_as_absent: boolean;
  late_label: string;
  late_family: "danger" | "warning";
  delta_vs_average: number | null;
  late_list: AttendanceStatsLate[];
  excused_list: AttendanceStatsExcused[];
  absent_list: MembershipBrief[];
}

export interface RankedNote {
  rank: number;
  player: MembershipBrief;
  note: string;
}

export interface NoteBucket {
  label: string;
  min: string;
  max: string;
  count: number;
}

export interface PlayerNoteComment {
  text: string;
  visible_to_player: boolean;
}

export interface PlayerNoteRow {
  player: MembershipBrief;
  overall: string;
  technical: string | null;
  physical: string | null;
  tactical: string | null;
  mental: string | null;
  attitude: string | null;
  evaluators_count: number;
  comments: PlayerNoteComment[];
}

/** Bloc « Notes du Coach » : `null` pour les rôles qui n'y ont pas droit. */
export interface SessionEvaluationStats {
  average: string | null;
  evaluated: number;
  eligible: number;
  remaining: number;
  delta_vs_average: string | null;
  ranking_available: boolean;
  best: RankedNote[];
  lowest: RankedNote[];
  distribution: NoteBucket[];
  players: PlayerNoteRow[];
  not_evaluated: MembershipBrief[];
  open_until: string;
  locked: boolean;
  hours_left: number | null;
}

export interface MyEvaluationStats {
  overall: string;
  criteria: {
    technical: string | null;
    physical: string | null;
    tactical: string | null;
    mental: string | null;
    attitude: string | null;
  };
  comments: string[];
}

/** Résumé des tests de performance de la séance (partie C, carte « Mesures de la séance »). */
export interface SessionMeasureSummary {
  test_id: number;
  name: string;
  kind: string;
  measured_count: number;
  best: { player: { membership_id: number; name: string }; display?: string } | null;
}

export interface SessionStats {
  session_id: number;
  date: string;
  generated_at: string;
  attendance: SessionAttendanceStats;
  evaluations: SessionEvaluationStats | null;
  my_evaluation: MyEvaluationStats | null;
  measures: SessionMeasureSummary[];
  capabilities: { can_evaluate: boolean; can_measure: boolean };
}

export function getSessionStats(sessionId: number) {
  return apiGet<SessionStats>(`/sport/sessions/${sessionId}/stats/`);
}

export interface SessionHistoryResult {
  session_id: number;
  date: string;
  location: string;
  expected: number;
  present: number;
  attendance_rate: number | null;
  /** Staff seulement, sinon `null`. */
  average_rating: string | null;
  my_rating: string | null;
  locked: boolean;
}

export interface SessionStatsHistory {
  period: StatsPeriod;
  season: { id: number; label: string } | null;
  average_attendance_rate: number | null;
  average_rating: string | null;
  my_average_rating: string | null;
  results: SessionHistoryResult[];
}

export function getSessionStatsHistory(period: StatsPeriod) {
  return apiGet<SessionStatsHistory>(`/sport/sessions/stats/history/?period=${period}`);
}

export interface AttendanceRankingEntry {
  player: MembershipBrief;
  sessions: number;
  attended: number;
  present: number;
  late: number;
  excused: number;
  absent: number;
  rate: number | null;
}

export interface AttendanceRanking {
  period: StatsPeriod;
  sessions_count: number;
  late_counts_as_absent: boolean;
  results: AttendanceRankingEntry[];
}

/** Coach, Assistant, Président, VP, DS ; 403 pour les autres. */
export function getAttendanceRanking(period: StatsPeriod) {
  return apiGet<AttendanceRanking>(`/sport/attendance/ranking/?period=${period}`);
}

export interface MyAttendance {
  period: StatsPeriod;
  sessions_count: number;
  sessions: number;
  attended: number;
  present: number;
  late: number;
  excused: number;
  absent: number;
  rate: number | null;
  late_counts_as_absent: boolean;
}

/** 404 si le compte n'a pas de fiche joueur dans le club. */
export function getMyAttendance(period: StatsPeriod) {
  return apiGet<MyAttendance>(`/sport/attendance/me/?period=${period}`);
}

// ---------------------------------------------------------------------------
// Matchs (CDC 4.8)
// ---------------------------------------------------------------------------

export type MatchType = "friendly" | "championship" | "tournament";
export type MatchVenue = "home" | "away";
export type ChallengeStatus = "n_a" | "proposed" | "accepted" | "declined";

export interface MatchListItem {
  id: number;
  event_date: string;
  kickoff_time: string;
  opponent: string;
  match_type: MatchType;
  venue: MatchVenue;
  is_composition_published: boolean;
  is_locked: boolean;
}

export interface CompositionEntry {
  id: number;
  membership_id: number;
  player: MembershipBrief;
  role: "starter" | "substitute";
  role_label: string;
  position: string;
  position_label: string;
  jersey_number: number;
  no_longer_eligible: ReasonInfo | null;
}

export interface Goal {
  id: number;
  scorer: MembershipBrief | null;
  assist: MembershipBrief | null;
  minute: number | null;
  updated_at: string | null;
}

export interface MatchSheet {
  score_home: number;
  score_away: number;
  filled_at: string;
  goals: Goal[];
}

export interface MatchDetail extends EventCommon {
  kickoff_time: string;
  opponent: string;
  match_type: MatchType;
  venue: MatchVenue;
  location: string;
  challenge_status: ChallengeStatus;
  is_composition_published: boolean;
  composition_published_at: string | null;
  attendances: Attendance[];
  attendance_counts: AttendanceCounts;
  starters: CompositionEntry[];
  substitutes: CompositionEntry[];
  sheet: MatchSheet | null;
  /** Vrai une fois le résultat publié sur le fil du club. */
  result_published?: boolean;
  capabilities?: AttendanceCapabilities;
}

export interface MatchInput {
  season_id?: number | null;
  event_date: string;
  kickoff_time: string;
  match_type: MatchType;
  venue: MatchVenue;
  location?: string;
  opponent_club_id?: number | null;
  opponent_name?: string;
  challenge_status?: ChallengeStatus;
  challenge_to_club_id?: number | null;
}

export interface MatchUpdateInput {
  event_date: string;
  kickoff_time: string;
  match_type: MatchType;
  venue: MatchVenue;
  location?: string;
  opponent_club_id?: number | null;
  opponent_name?: string;
}

export function listMatches(params: { limit?: number; offset?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<{ count: number; next_offset: number | null; results: MatchListItem[] }>(
    `/sport/matches/${suffix}`,
  );
}

export function createMatch(input: MatchInput) {
  return apiPost<MatchDetail>("/sport/matches/", input);
}

export function getMatch(id: number) {
  return apiGet<MatchDetail>(`/sport/matches/${id}/`);
}

export function updateMatch(id: number, input: MatchUpdateInput) {
  return apiPatch<MatchDetail>(`/sport/matches/${id}/`, input);
}

export function markMatchAttendance(matchId: number, input: AttendanceMarkInput) {
  return apiPost<Attendance>(`/sport/matches/${matchId}/attendance/`, input);
}

export interface CompositionInput {
  membership_id: number;
  role: "starter" | "substitute";
  position: string;
  jersey_number: number;
}

export function addToComposition(matchId: number, input: CompositionInput) {
  return apiPost<CompositionEntry>(`/sport/matches/${matchId}/composition/`, input);
}

/**
 * Éligibilité groupée des joueurs du club actif (`GET /sport/eligibility/`,
 * sport-feuille-de-match.md §4.1 bis). Réservée au Coach et à l'Assistant du
 * Coach (403 pour les autres rôles). `reason` est le texte lisible fourni par
 * l'API (« En dette : 10.00 USD. ») : l'interface ne le recompose jamais.
 */
export type EligibilityReasonCode = "debt" | "suspension" | "unfit" | "pending_membership" | "";

export interface EligibilityItem {
  membership_id: number;
  eligible: boolean;
  reason_code: EligibilityReasonCode;
  reason: string;
}

export function listEligibility() {
  return apiGet<{ count: number; results: EligibilityItem[] }>("/sport/eligibility/");
}

export function removeFromComposition(matchId: number, membershipId: number) {
  return apiDelete<void>(`/sport/matches/${matchId}/composition/${membershipId}/`);
}

export function publishComposition(matchId: number) {
  return apiPost<MatchDetail>(`/sport/matches/${matchId}/composition/publish/`);
}

export function publishMatchResult(matchId: number) {
  return apiPost<MatchDetail>(`/sport/matches/${matchId}/publish-result/`);
}

export function setMatchScore(matchId: number, input: { score_home: number; score_away: number }) {
  return apiPost<MatchDetail>(`/sport/matches/${matchId}/score/`, input);
}

export function listMatchGoals(matchId: number) {
  return apiGet<Goal[]>(`/sport/matches/${matchId}/goals/`);
}

export interface GoalInput {
  scorer_membership_id?: number | null;
  assist_membership_id?: number | null;
  minute?: number | null;
}

export function addGoal(matchId: number, input: GoalInput) {
  return apiPost<Goal>(`/sport/matches/${matchId}/goals/`, input);
}

export function updateGoal(goalId: number, input: GoalInput) {
  return apiPatch<Goal>(`/sport/goals/${goalId}/`, input);
}

export function deleteGoal(goalId: number) {
  return apiDelete<void>(`/sport/goals/${goalId}/`);
}

// ---------------------------------------------------------------------------
// Plan tactique (CDC 4.11)
// ---------------------------------------------------------------------------

export type Formation =
  | "4-4-2"
  | "4-3-3"
  | "4-2-3-1"
  | "3-5-2"
  | "3-4-3"
  | "5-3-2"
  | "4-1-4-1"
  | "4-5-1"
  | "custom";

export type SquadSize = 7 | 8 | 11;

export interface TacticalPlanListItem {
  id: number;
  name: string;
  formation: Formation;
  squad_size: SquadSize;
  match_id: number | null;
  is_published: boolean;
  published_at: string | null;
  updated_at: string;
}

export interface Placement {
  id: number;
  membership_id: number | null;
  player: MembershipBrief | null;
  x_coord: string;
  y_coord: string;
  jersey_number_override: number | null;
  position_override: string;
  no_longer_eligible: ReasonInfo | null;
  warning?: string | null;
}

export interface Annotation {
  id: number;
  annotation_type: "arrow" | "zone" | "note";
  path_data: string;
  text: string;
  target_membership_id: number | null;
  target_line: "defense" | "midfield" | "attack" | "";
}

export interface TacticalPlanDetail extends TacticalPlanListItem {
  created_at: string;
  placements: Placement[];
  annotations: Annotation[];
}

export interface TacticalPlanInput {
  name: string;
  formation: Formation;
  squad_size: SquadSize;
  match_id?: number | null;
}

export function listTacticalPlans(params: { status?: "published" | "draft"; limit?: number; offset?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<{ count: number; next_offset: number | null; results: TacticalPlanListItem[] }>(
    `/sport/tactical-plans/${suffix}`,
  );
}

export function createTacticalPlan(input: TacticalPlanInput) {
  return apiPost<TacticalPlanDetail>("/sport/tactical-plans/", input);
}

export function getTacticalPlan(id: number) {
  return apiGet<TacticalPlanDetail>(`/sport/tactical-plans/${id}/`);
}

export function updateTacticalPlanSettings(id: number, input: TacticalPlanInput) {
  return apiPatch<TacticalPlanDetail>(`/sport/tactical-plans/${id}/`, input);
}

export function deleteTacticalPlan(id: number) {
  return apiDelete<void>(`/sport/tactical-plans/${id}/`);
}

export function duplicateTacticalPlan(id: number, input: { name: string; match_id?: number | null }) {
  return apiPost<TacticalPlanDetail & { skipped_count: number }>(`/sport/tactical-plans/${id}/duplicate/`, input);
}

export function publishTacticalPlan(id: number) {
  return apiPost<TacticalPlanDetail>(`/sport/tactical-plans/${id}/publish/`);
}

export function placeOnPlan(planId: number, input: { membership_id: number; x_coord: number; y_coord: number }) {
  return apiPost<Placement>(`/sport/tactical-plans/${planId}/placements/`, input);
}

export function updatePlacement(
  placementId: number,
  input: { jersey_number?: number | null; position?: string },
) {
  return apiPatch<Placement>(`/sport/placements/${placementId}/`, input);
}

export function removePlacement(placementId: number) {
  return apiDelete<void>(`/sport/placements/${placementId}/`);
}

export interface AnnotationInput {
  annotation_type: "arrow" | "zone" | "note";
  path_data?: string;
  text?: string;
  target_membership_id?: number | null;
  target_line?: "defense" | "midfield" | "attack" | "";
}

export function addAnnotation(planId: number, input: AnnotationInput) {
  return apiPost<Annotation>(`/sport/tactical-plans/${planId}/annotations/`, input);
}

export function removeAnnotation(annotationId: number) {
  return apiDelete<void>(`/sport/annotations/${annotationId}/`);
}

// ---------------------------------------------------------------------------
// Vestiaire du jour (lecture seule)
// ---------------------------------------------------------------------------

export interface MySituation {
  attendance: Attendance | null;
  team: "A" | "B" | null;
  eligible: boolean;
  reason: string;
  reason_code: string;
}

/**
 * Prochain évènement à venir (séance ou match), renvoyé par `/sport/locker-room/`
 * en plus de l'évènement du jour — ajouté par `backend-dev` pour que la page
 * Vestiaire et la carte « Prochain rendez-vous » de l'accueil puissent
 * afficher une précision quand rien n'a lieu exactement aujourd'hui
 * (`sport-vestiaire.md` §6, `club-accueil.md` §4 point 5). `location` est
 * une chaîne vide, jamais `null` ; `null` quand aucun évènement futur n'est
 * programmé.
 */
export interface NextEventSession {
  type: "session";
  id: number;
  event_date: string;
  gathering_time: string;
  location: string;
}

export interface NextEventMatch {
  type: "match";
  id: number;
  event_date: string;
  kickoff_time: string;
  opponent: string;
  location: string;
}

export type NextEvent = NextEventSession | NextEventMatch;

export interface LockerRoom {
  session: SessionDetail | null;
  match: MatchDetail | null;
  my_situation: MySituation | null;
  next_event: NextEvent | null;
}

export function getLockerRoom() {
  return apiGet<LockerRoom>("/sport/locker-room/");
}

// ---------------------------------------------------------------------------
// Pointage groupé (docs/ecrans/sport-pointage-selection-multiple.md §7)
// ---------------------------------------------------------------------------

export type BulkAttendanceAction = "arrive" | "excuse";
export type BulkExcuseReasonCode = "injured" | "travel" | "other";

export interface BulkAttendanceItem {
  membership_id: number;
  client_uuid?: string;
  client_recorded_at?: string;
  selection_rank?: number;
}

export interface BulkAttendanceInput {
  action: BulkAttendanceAction;
  arrived_at?: string;
  reason_code?: BulkExcuseReasonCode;
  reason_detail?: string;
  items: BulkAttendanceItem[];
}

export interface BulkAttendanceResult {
  membership_id: number;
  outcome: "created" | "skipped" | "refused";
  message: string;
  attendance: Attendance | null;
}

export interface BulkAttendanceResponse {
  batch_id: string;
  results: BulkAttendanceResult[];
  counts: { created: number; skipped: number; refused: number };
}

/** Taille maximale d'un lot acceptée par l'API. */
export const BULK_ATTENDANCE_MAX_ITEMS = 100;

export function bulkMarkAttendance(kind: "session" | "match", eventId: number, input: BulkAttendanceInput) {
  const base = kind === "session" ? "sessions" : "matches";
  return apiPost<BulkAttendanceResponse>(`/sport/${base}/${eventId}/attendance/bulk/`, input);
}
