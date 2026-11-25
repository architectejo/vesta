/**
 * Appels de l'app `clubs` (CDC 2.2-2.4, 4.1, 4.3 ; tâche 1.9). Contrats lus
 * directement dans `backend/apps/clubs/{urls,views,serializers}.py`.
 */

import { apiDownload, apiGet, apiPatch, apiPost } from "./client";
import type { TermsVersion } from "./auth";
import type { PlayerSearchResult } from "../design-system/components/PlayerSearch";

// ---------------------------------------------------------------------------
// Assistant de création de club (public)
// ---------------------------------------------------------------------------

export interface PublicClubCreationSettings {
  trial_duration_days: number;
  grace_period_days: number;
  timezones: string[];
  terms_version: TermsVersion | null;
}

export function getPublicClubCreationSettings() {
  return apiGet<PublicClubCreationSettings>("/clubs/public/creation-settings/", { auth: false });
}

export interface ClubCreationInput {
  idempotency_key: string;
  name: string;
  logo?: File | null;
  primary_color?: string;
  secondary_color?: string;
  city: string;
  country: string;
  currency: "USD" | "CDF";
  timezone_name: string;
  email: string;
  first_name: string;
  last_name: string;
  phone?: string;
  position: "goalkeeper" | "defender" | "midfielder" | "forward";
  position_detail?: string;
  jersey_number?: number | null;
  birth_date?: string | null;
  weight_kg?: number | null;
  height_cm?: number | null;
  terms_version_id: number;
  accept_terms: boolean;
}

export interface ClubCreationSuccess {
  access: string;
  refresh: string;
  user: {
    id: number;
    email: string;
    first_name: string;
    last_name: string;
    is_superuser: boolean;
    must_change_password: boolean;
    preferred_theme: string;
  };
  club: {
    id: number;
    slug: string;
    name: string;
    logo: string | null;
    primary_color: string;
    secondary_color: string;
    city: string;
    country: string;
  };
  licence: { status: string; end_date: string };
  must_change_password: boolean;
  terms_acceptance_required: boolean;
}

function toFormData(input: ClubCreationInput): FormData {
  const form = new FormData();
  for (const [key, value] of Object.entries(input)) {
    if (value === undefined || value === null) continue;
    if (value instanceof File) {
      form.append(key, value);
    } else {
      form.append(key, String(value));
    }
  }
  return form;
}

export function createClub(input: ClubCreationInput) {
  return apiPost<ClubCreationSuccess>("/clubs/create/", toFormData(input), { auth: false });
}

// ---------------------------------------------------------------------------
// Mon profil (agrégation en lecture, slice Lot 1)
// ---------------------------------------------------------------------------

export interface MyProfile {
  membership_id: number;
  club: {
    id: number;
    slug: string;
    name: string;
    logo: string | null;
    primary_color: string;
    secondary_color: string;
  };
  identity: {
    first_name: string;
    last_name: string;
    photo: string | null;
    email: string;
    phone: string;
    birth_date: string | null;
    weight_kg: string | null;
    height_cm: string | null;
  };
  position: string;
  position_label: string;
  position_detail: string;
  jersey_number: number | null;
  membership_status: string;
  membership_status_label: string;
  roles: Array<{ role: string; label: string }>;
  email_notifications_enabled: boolean;
  /** Destination d'arrivée décidée par l'API. */
  default_landing?: "board_dashboard" | "home";
  /** Droits de page calculés par l'API (jamais déduits d'un rôle côté interface). */
  capabilities?: { can_view_board_dashboard?: boolean };
}

export function getMyProfile() {
  return apiGet<MyProfile>("/clubs/profile/me/");
}

// ---------------------------------------------------------------------------
// Identité du club (club-comite-bureau.md §4.1)
// ---------------------------------------------------------------------------

export interface ClubIdentity {
  id: number;
  name: string;
  slug: string;
  logo: string | null;
  primary_color: string;
  secondary_color: string;
  city: string;
  country: string;
  currency: "USD" | "CDF";
  currency_locked: boolean;
  timezone: string;
  payment_link_url?: string;
  payment_link_configured?: boolean;
  /** Jours de tolérance avant qu'un retard devienne une dette (0 à 90). */
  debt_tolerance_days?: number;
}

export function getClubIdentity() {
  return apiGet<ClubIdentity>("/clubs/settings/identity/");
}

export interface ClubIdentityUpdateInput {
  name?: string;
  logo?: File | null;
  primary_color?: string;
  secondary_color?: string;
  city?: string;
  country?: string;
  currency?: "USD" | "CDF";
  timezone?: string;
  payment_link_url?: string;
  /** Président seul (403 sinon) ; entier 0 à 90. */
  debt_tolerance_days?: number;
}

export function updateClubIdentity(input: ClubIdentityUpdateInput) {
  const hasFile = input.logo instanceof File;
  if (hasFile) {
    const form = new FormData();
    for (const [key, value] of Object.entries(input)) {
      if (value === undefined || value === null) continue;
      form.append(key, value instanceof File ? value : String(value));
    }
    return apiPatch<ClubIdentity>("/clubs/settings/identity/", form);
  }
  const { logo: _logo, ...rest } = input;
  return apiPatch<ClubIdentity>("/clubs/settings/identity/", rest);
}

// ---------------------------------------------------------------------------
// Fiche publique du joueur (club-comite-bureau.md §4.7)
// ---------------------------------------------------------------------------

export interface PlayerPublicCard {
  membership_id: number;
  first_name: string;
  last_name: string;
  photo: string | null;
  position: string;
  position_label: string;
  position_detail: string;
  jersey_number: number | null;
  membership_status: string;
  membership_status_label: string;
  joined_on: string | null;
  roles: Array<{ role: string; label: string }>;
  /** Booléen sans motif, servi à tous les rôles (10.2 n° 16). */
  is_unavailable?: boolean;
}

export function getPlayerCard(membershipId: number) {
  return apiGet<PlayerPublicCard>(`/clubs/players/${membershipId}/card/`);
}

// ---------------------------------------------------------------------------
// Effectif : liste et recherche des joueurs du club (club-comite-bureau.md
// §3.6 « Effectif », §4.2 « Rôle », §4.3 « Transmettre la présidence », §4.4
// « Joueurs autorisés à ajouter des joueurs », §4.5 « Ajouter un joueur »
// champ Parrain). Aucune donnée financière ni médicale (même garde que
// `PlayerCardView`).
// ---------------------------------------------------------------------------

export type ClubPlayerPosition = "goalkeeper" | "defender" | "midfielder" | "forward";
export type ClubPlayerMembershipStatus = "pending" | "active" | "departed";

export interface ClubPlayerListItem {
  membership_id: number;
  first_name: string;
  last_name: string;
  photo: string | null;
  position: ClubPlayerPosition;
  position_label: string;
  position_detail: string;
  jersey_number: number | null;
  membership_status: ClubPlayerMembershipStatus;
  membership_status_label: string;
  roles: Array<{ role: string; label: string }>;
  /** Booléen sans motif, servi à tous les rôles (10.2 n° 16). */
  is_unavailable?: boolean;
}

export interface ListClubPlayersParams {
  /** Filtre prénom/nom, insensible à la casse ; limité à 50 résultats côté API. */
  search?: string;
  position?: ClubPlayerPosition;
  status?: ClubPlayerMembershipStatus;
  role?: string;
}

export function listClubPlayers(params: ListClubPlayersParams = {}) {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.position) query.set("position", params.position);
  if (params.status) query.set("status", params.status);
  if (params.role) query.set("role", params.role);
  const qs = query.toString();
  return apiGet<ClubPlayerListItem[]>(`/clubs/players/${qs ? `?${qs}` : ""}`);
}

/** Adapte un élément de l'effectif au format attendu par `PlayerSearch`. */
export function toPlayerSearchResult(item: ClubPlayerListItem): PlayerSearchResult {
  return {
    id: item.membership_id,
    firstName: item.first_name,
    lastName: item.last_name,
    number: item.jersey_number,
    position: item.position_label,
    photoUrl: item.photo,
  };
}

/**
 * Fonction `searchPlayers` prête à l'emploi pour `PlayerSearch` /
 * `PlayerMultiSearch`, bornée aux joueurs **inscrits** du club
 * (`status: "active"`). C'est la portée demandée par chacun des écrans qui
 * choisissent un joueur déjà membre du club : parrain (§4.5 : « joueurs
 * inscrits seulement »), nomination de rôle et remplacement de titulaire
 * (§4.2), transmission de la présidence (§4.3) et joueurs autorisés à
 * ajouter des joueurs (§4.4). Aucun autre filtre n'est appliqué : ce n'est
 * pas à l'interface de décider qui est éligible à un rôle donné.
 */
export function searchActiveClubPlayers(query: string): Promise<PlayerSearchResult[]> {
  return listClubPlayers({ status: "active", search: query }).then((items) =>
    items.map(toPlayerSearchResult),
  );
}

// ---------------------------------------------------------------------------
// Rôles (CDC 2.3)
// ---------------------------------------------------------------------------

export interface MembershipRole {
  id: number;
  membership_id: number;
  role: string;
  role_label: string;
  effective_label: string;
  is_qualified_professional: boolean | null;
  appointed_by_id: number;
  appointed_at: string;
  revoked_by_id: number | null;
  revoked_at: string | null;
  revoked_reason: string;
}

export function listRoles() {
  return apiGet<MembershipRole[]>("/clubs/roles/");
}

export function appointRole(params: {
  membership_id: number;
  role: string;
  is_qualified_professional?: boolean | null;
}) {
  return apiPost<MembershipRole>("/clubs/roles/appoint/", params);
}

export function revokeRole(params: { role_id: number; reason?: string }) {
  return apiPost<MembershipRole>("/clubs/roles/revoke/", params);
}

export function appointAssistantCoach(params: { membership_id: number }) {
  return apiPost<MembershipRole>("/clubs/roles/assistant-coach/appoint/", params);
}

export function revokeAssistantCoach(params: { role_id: number; reason?: string }) {
  return apiPost<MembershipRole>("/clubs/roles/assistant-coach/revoke/", params);
}

export function appointCaptain(params: { membership_id: number }) {
  return apiPost<MembershipRole>("/clubs/roles/captain/appoint/", params);
}

export function revokeCaptain(params: { role_id: number; reason?: string }) {
  return apiPost<MembershipRole>("/clubs/roles/captain/revoke/", params);
}

export function handoverPresidency(params: { to_membership_id: number; reason?: string }) {
  return apiPost<{ id: number }>("/clubs/presidency-transfer/handover/", params);
}

export interface BoardSeatsSettings {
  board_seats_per_role: number;
  updated_at: string | null;
  updated_by_id: number | null;
}

export function getBoardSeats() {
  return apiGet<BoardSeatsSettings>("/clubs/settings/board-seats/");
}

export function updateBoardSeats(boardSeatsPerRole: number) {
  return apiPatch<BoardSeatsSettings>("/clubs/settings/board-seats/", {
    board_seats_per_role: boardSeatsPerRole,
  });
}

// ---------------------------------------------------------------------------
// Import et ajout de joueurs (CDC 4.1, 4.3)
// ---------------------------------------------------------------------------

export interface ImportBatch {
  id: number;
  import_type: string;
  imported_by_id: number;
  imported_at: string;
  row_count_success: number;
  row_count_failed: number;
  report_file: string | null;
  failed_rows: Array<{ line_number: number; message: string }>;
}

export function importPlayers(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiPost<ImportBatch>("/clubs/players/import/", form);
}

export interface AddPlayerWithSponsorInput {
  email: string;
  first_name: string;
  last_name: string;
  phone?: string;
  position: "goalkeeper" | "defender" | "midfielder" | "forward";
  position_detail?: string;
  jersey_number?: number | null;
  birth_date?: string | null;
  weight_kg?: number | null;
  height_cm?: number | null;
  sponsor_membership_id: number;
  requested_contribution_type_label?: string;
}

export type SponsorDecision = "pending" | "signed" | "refused";
export type FeeDisposition = "refunded" | "kept" | "";

export interface ApplicationPerson {
  membership_id: number;
  first_name: string;
  last_name: string;
  photo: string | null;
  position_label: string;
  jersey_number: number | null;
}

export interface MembershipApplication {
  id: number;
  membership_id: number;
  /** Joueur concerné et parrain actuel (lecture seule, servis par l'API). */
  player?: ApplicationPerson | null;
  sponsor?: ApplicationPerson | null;
  membership_status?: "pending" | "active" | "departed";
  membership_fee_paid?: boolean;
  membership_fee_amount?: string | null;
  membership_fee_paid_on?: string | null;
  /** Adresse de la vue authentifiée de la fiche PDF (jamais une URL publique). */
  application_pdf_url: string | null;
  generated_at: string | null;
  sponsor_notified_at: string | null;
  sponsor_decision: SponsorDecision;
  sponsor_signed_by_id: number | null;
  sponsor_signed_at: string | null;
  sponsor_refused_reason: string;
  sponsor_reminder_sent_at: string | null;
  president_alerted_at: string | null;
  resolved_at: string | null;
  cancelled_by_id: number | null;
  cancelled_reason: string;
  membership_fee_payment_id: number | null;
  membership_fee_disposition: FeeDisposition;
}

export function addPlayerWithSponsor(input: AddPlayerWithSponsorInput) {
  return apiPost<{ membership_id: number; application: MembershipApplication }>(
    "/clubs/players/add/",
    input,
  );
}

// ---------------------------------------------------------------------------
// Parcours d'adhésion et de parrainage (CDC 4.3 ; club-accueil.md §5.4, §5.5)
// ---------------------------------------------------------------------------

/** Dossier d'adhésion d'un joueur ; 404 si le joueur n'a pas de dossier. */
export function getMembershipApplication(membershipId: number) {
  return apiGet<MembershipApplication>(`/clubs/players/${membershipId}/application/`);
}

/** Fiches que l'utilisateur connecté doit signer en tant que parrain. */
export function listPendingSponsorSignatures() {
  return apiGet<MembershipApplication[]>("/clubs/applications/pending-sponsor-signature/");
}

export interface PendingPresidentDecisions {
  /** Parrainages refusés : décision à prendre (autre parrain ou annulation). */
  refused: MembershipApplication[];
  /** Parrains sans réponse depuis 7 jours : alerte seule (CDC 10.3 n° 71). */
  awaiting_sponsor: MembershipApplication[];
}

export function listPendingPresidentDecisions() {
  return apiGet<PendingPresidentDecisions>("/clubs/applications/pending-president-decision/");
}

export function signSponsorApplication(params: { application_id: number }) {
  return apiPost<MembershipApplication>("/clubs/applications/sponsor/sign/", params);
}

export function refuseSponsorApplication(params: { application_id: number; reason: string }) {
  return apiPost<MembershipApplication>("/clubs/applications/sponsor/refuse/", params);
}

export function reassignSponsor(params: { application_id: number; new_sponsor_membership_id: number }) {
  return apiPost<MembershipApplication>("/clubs/applications/sponsor/reassign/", params);
}

export function cancelMembershipApplication(params: {
  application_id: number;
  reason: string;
  disposition: "refunded" | "kept";
}) {
  return apiPost<MembershipApplication>("/clubs/applications/cancel/", params);
}

export interface MembershipFeePaymentInput {
  application_id: number;
  amount: string;
  method: "cash" | "mobile_money" | "payment_link";
  paid_on: string;
  reference?: string;
  /** UUID v4 d'idempotence ; jamais envoyé vide (ignoré par la boucle ci-dessous). */
  client_uuid?: string;
}

export function recordMembershipFeePayment(input: MembershipFeePaymentInput) {
  const form = new FormData();
  for (const [key, value] of Object.entries(input)) {
    if (value === undefined || value === null || value === "") continue;
    form.append(key, String(value));
  }
  return apiPost<MembershipApplication>("/clubs/applications/fee-payment/", form);
}

/** Télécharge la fiche d'adhésion PDF par la vue authentifiée. */
export function downloadApplicationPdf(applicationId: number) {
  return apiDownload(`/clubs/applications/${applicationId}/fiche-pdf/`, `adhesion-${applicationId}.pdf`);
}
