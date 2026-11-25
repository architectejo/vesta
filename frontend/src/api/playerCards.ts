/**
 * Cartes des joueurs et statistiques (docs/ecrans/club-cartes-joueurs.md §7 ;
 * CDC 4.2). Contrat lu dans `backend/apps/sport/player_stats.py` et
 * `backend/apps/clubs/views_player_cards.py`. Lecture seule ; aucune règle
 * métier ici : tout est calculé par l'API.
 */

import { apiGet } from "./client";
import type { ClubPlayerPosition } from "./clubs";

export type PlayerCardOrderingKey =
  | "name"
  | "number"
  | "average_rating"
  | "goals"
  | "assists"
  | "attendance_rate"
  | "matches_played";

/** Clé de tri, avec le préfixe « - » pour le tri décroissant (« Buts » = `-goals`). */
export type PlayerCardOrdering = PlayerCardOrderingKey | `-${PlayerCardOrderingKey}`;

export type PlayerCardStatusFilter = "active" | "left";
export type PlayerCardAvailabilityFilter = "available" | "unavailable";

/** Les six indicateurs sportifs ; `average_rating` est une chaîne décimale (« 6.8 »). */
export interface PlayerSeasonStats {
  matches_played: number;
  goals: number;
  assists: number;
  yellow_cards: number;
  red_cards: number;
  attendance_rate: number | null;
  average_rating: string | null;
}

export type PlayerAvailabilityFamily = "suspension" | "unfit" | "pending" | "unavailable";

export interface PlayerCardAvailability {
  label: string;
  family: PlayerAvailabilityFamily;
}

export interface PlayerCardListRow {
  membership_id: number;
  first_name: string;
  last_name: string;
  photo: string | null;
  jersey_number: number | null;
  position: ClubPlayerPosition | "";
  position_label: string;
  position_detail: string;
  overall_rating: number | null;
  stats: PlayerSeasonStats;
  recent_ratings: string[];
  /** Rempli pour le staff seulement ; une dette n'y est jamais nommée. */
  availability: PlayerCardAvailability | null;
}

export interface PlayerCardSeason {
  id: number;
  label: string;
  is_current: boolean;
}

export interface PlayerCardListResponse {
  count: number;
  limit: number;
  offset: number;
  has_more: boolean;
  season_id: number | null;
  season_label: string | null;
  seasons: PlayerCardSeason[];
  can_see_availability: boolean;
  can_compare: boolean;
  results: PlayerCardListRow[];
}

export interface PlayerCardListParams {
  search?: string;
  position?: ClubPlayerPosition;
  status?: PlayerCardStatusFilter;
  availability?: PlayerCardAvailabilityFilter;
  season?: number;
  ordering?: PlayerCardOrdering;
  limit?: number;
  offset?: number;
}

export function listPlayerCards(params: PlayerCardListParams = {}) {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.position) query.set("position", params.position);
  if (params.status) query.set("status", params.status);
  if (params.availability) query.set("availability", params.availability);
  if (params.season !== undefined) query.set("season", String(params.season));
  if (params.ordering) query.set("ordering", params.ordering);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  return apiGet<PlayerCardListResponse>(`/clubs/players/cards/${qs ? `?${qs}` : ""}`);
}

// ---------------------------------------------------------------------------
// Statistiques détaillées d'un joueur
// ---------------------------------------------------------------------------

export interface RadarAxisValue {
  key: string;
  label: string;
  /** Sur 10, chaîne décimale (« 6.0 »), ou `null` : pas encore d'évaluation. */
  value: string | null;
}

export interface PlayerRadar {
  axes: RadarAxisValue[];
}

export interface PlayerRecentFormEntry {
  date: string;
  event_type: string;
  label: string;
  rating: string;
}

export interface PlayerAttendance {
  sessions_expected: number;
  sessions_present: number;
  late: number;
  excused: number;
  absent: number;
  rate: number | null;
  late_counts_as_absent: boolean;
}

export interface PlayerDisciplineCard {
  id: number;
  date: string;
  event_kind: string;
  incident_type: string;
  incident_type_label: string;
  cause: string;
  cause_label: string;
  minute: number | null;
}

export interface PlayerActiveSuspension {
  reason: string;
  reason_label: string;
  matches_total: number;
  matches_served: number;
  matches_remaining: number;
  label: string;
}

export interface PlayerDiscipline {
  cards: PlayerDisciplineCard[];
  /** `null` sauf staff et joueur lui-même. */
  active_suspension: PlayerActiveSuspension | null;
}

export type PlayerFitnessStatus = "fit" | "fit_with_restriction" | "unfit";

export interface PlayerFitness {
  status: PlayerFitnessStatus;
  label: string;
  return_date: string | null;
}

export interface PlayerPerformanceTest {
  test: { id: number; name: string; kind_text?: string };
  best: { date: string; display: string | null };
  last?: { date: string; display: string | null };
  results_count?: number;
}

export interface PlayerStatsResponse {
  membership_id: number;
  season_id: number | null;
  season_label: string | null;
  overall_rating: number | null;
  stats: PlayerSeasonStats;
  radar: PlayerRadar;
  recent_form: PlayerRecentFormEntry[];
  attendance: PlayerAttendance;
  discipline: PlayerDiscipline;
  /** `null` sauf staff et joueur lui-même (jamais de diagnostic). */
  fitness: PlayerFitness | null;
  /** `null` sauf staff et joueur lui-même. */
  performance: PlayerPerformanceTest[] | null;
}

export function getPlayerStats(membershipId: number, season?: number | null) {
  const qs = season ? `?season=${season}` : "";
  return apiGet<PlayerStatsResponse>(`/clubs/players/${membershipId}/stats/${qs}`);
}

// ---------------------------------------------------------------------------
// Comparaison de 2 à 4 joueurs
// ---------------------------------------------------------------------------

export interface ComparedPlayerConsultable {
  membership_id: number;
  first_name: string;
  last_name: string;
  photo: string | null;
  jersey_number: number | null;
  position: ClubPlayerPosition | "";
  position_label: string;
  consultable: true;
  /** `club` : joueur du club actif ; `public` : joueur d'un autre club (données publiques). */
  scope: "club" | "public";
  club: { id: number; name: string; logo: string | null };
  season_id: number | null;
  season_label: string | null;
  overall_rating: number | null;
  stats: PlayerSeasonStats;
  radar: PlayerRadar | null;
}

export interface ComparedPlayerUnavailable {
  membership_id: number;
  consultable: false;
  detail: string;
}

export type ComparedPlayer = ComparedPlayerConsultable | ComparedPlayerUnavailable;

export interface PlayerComparisonResponse {
  count: number;
  results: ComparedPlayer[];
}

export function comparePlayers(ids: number[]) {
  return apiGet<PlayerComparisonResponse>(`/clubs/players/compare/?ids=${ids.join(",")}`);
}
