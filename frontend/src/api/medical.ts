/**
 * Appels de l'app `medical` (Lot 4, tâche 4.12). Contrats lus directement
 * dans `backend/apps/medical/{urls,views,serializers}.py` : aucune forme
 * n'est devinée ici (docs/ecrans/medical.md fait référence pour les
 * textes et règles d'affichage — §0 du document).
 *
 * Non-divulgation (medical.md §5.4) : les réponses N2 (fiche complète,
 * détail d'une blessure) ne doivent jamais être mises en cache par
 * l'interface — chaque appelant utilise `gcTime: 0` et invalide/efface la
 * requête à la fermeture de la modale concernée.
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

// ---------------------------------------------------------------------------
// Types communs
// ---------------------------------------------------------------------------

export type FitnessStatus = "fit" | "fit_with_restriction" | "unfit";

export interface MembershipBrief {
  membership_id: number;
  name: string;
  jersey_number: number | null;
}

/** N1 (medical.md §5.1 point 1) : forme unique, jamais enrichie. */
export interface FitnessSummary {
  fitness_status: FitnessStatus;
  fitness_return_date: string | null;
}

/** Ligne « Inaptes et restrictions » (§3.2). */
export interface FitnessListItem extends MembershipBrief {
  fitness_status: FitnessStatus;
  fitness_return_date: string | null;
  fitness_return_date_label: string | null;
  /** Présent seulement pour un lecteur N2 (Médecin, Président avec
   * consentement pour CE joueur) — absent sinon (§5.1 point 5). */
  badge_injured?: boolean;
}

export type InjuryStatus = "open" | "resolved";

export interface InjuryListItem {
  id: number;
  membership_id: number;
  reported_at: string;
  status: InjuryStatus;
  location_on_body: string;
  event_id: number | null;
  doctor_completed: boolean;
  /** Pas encore renvoyé par l'API (gap signalé au compte rendu, medical.md
   * §3.1/§3.4) : intitulé « Séance du … »/« Match contre … », composé côté
   * serveur — voir `medicalLabels.injuryEventLabel`. */
  event_label?: string | null;
}

export interface InjuryFollowUp {
  id: number;
  entry_date: string;
  note: string;
  created_by: string;
  created_at: string;
}

export type InjurySeverity = "" | "mild" | "moderate" | "severe";
export type InjuryReferral = "" | "rest" | "consultation" | "hospital";

export interface InjuryDetail {
  id: number;
  membership_id: number;
  status: InjuryStatus;
  reported_by: string;
  reported_at: string;
  event_id: number | null;
  /** Voir la note sur `InjuryListItem.event_label`. */
  event_label?: string | null;
  occurred_time: string | null;
  occurred_minute: number | null;
  circumstances: string;
  location_on_body: string;
  severity: InjurySeverity;
  on_site_care: string;
  referral: InjuryReferral;
  estimated_days_out: number | null;
  doctor_completed_by: string | null;
  doctor_completed_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  followups: InjuryFollowUp[];
}

export type BloodGroup = "" | "A+" | "A-" | "B+" | "B-" | "AB+" | "AB-" | "O+" | "O-";

/** N2 (§4.2, §4.10) : dossier complet, réservé au Médecin, au joueur
 * concerné, ou au Président avec un consentement actif. */
export interface HealthRecordFull extends MembershipBrief {
  fitness_status: FitnessStatus;
  fitness_return_date: string | null;
  fitness_set_by: string | null;
  fitness_set_at: string | null;
  blood_group: BloodGroup;
  allergies: string;
  medical_history: string;
  ongoing_treatments: string;
  emergency_contact_name: string;
  emergency_contact_phone: string;
  self_declaration: string;
  self_declaration_updated_at: string | null;
  consent_given_at: string | null;
  open_injuries: InjuryListItem[];
  resolved_injuries: InjuryListItem[];
}

export interface ConsentStatus {
  /** État EFFECTIF (règle de la passation, §4.11) : jamais la présence
   * brute de `granted_at`. */
  granted: boolean;
  granted_at: string | null;
}

// ---------------------------------------------------------------------------
// Fiche de santé (§4.2, §4.5)
// ---------------------------------------------------------------------------

export function getHealthRecord(membershipId: number) {
  return apiGet<HealthRecordFull>(`/medical/players/${membershipId}/health-record/`);
}

export interface HealthRecordUpdateInput {
  blood_group?: BloodGroup;
  allergies?: string;
  medical_history?: string;
  ongoing_treatments?: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
}

export function updateHealthRecord(membershipId: number, input: HealthRecordUpdateInput) {
  return apiPatch<HealthRecordFull>(`/medical/players/${membershipId}/health-record/`, input);
}

export function updateFitness(
  membershipId: number,
  input: { fitness_status: FitnessStatus; fitness_return_date?: string | null },
) {
  return apiPatch<HealthRecordFull>(`/medical/players/${membershipId}/fitness/`, input);
}

// ---------------------------------------------------------------------------
// Mon profil (§4.10, §4.11)
// ---------------------------------------------------------------------------

export function updateMySelfDeclaration(input: { self_declaration?: string; consent_given?: boolean }) {
  return apiPatch<HealthRecordFull>("/medical/me/self-declaration/", input);
}

export function giveMyProcessingConsent() {
  return apiPost<{ consent_given_at: string }>("/medical/me/processing-consent/");
}

export function getMyPresidentAccess() {
  return apiGet<ConsentStatus>("/medical/me/president-access/");
}

export function grantMyPresidentAccess() {
  return apiPost<ConsentStatus>("/medical/me/president-access/");
}

export function revokeMyPresidentAccess() {
  return apiDelete<ConsentStatus>("/medical/me/president-access/");
}

// ---------------------------------------------------------------------------
// Blessures (§4.1, §4.3, §4.7-§4.9)
// ---------------------------------------------------------------------------

export interface InjuryReportInput {
  membership_id: number;
  event_id?: number | null;
  occurred_time?: string | null;
  occurred_minute?: number | null;
  circumstances: string;
}

export function reportInjury(input: InjuryReportInput) {
  return apiPost<InjuryDetail>("/medical/injuries/", input);
}

export function getInjury(id: number) {
  return apiGet<InjuryDetail>(`/medical/injuries/${id}/`);
}

export interface InjuryCompleteInput {
  location_on_body?: string;
  severity?: InjurySeverity;
  on_site_care?: string;
  referral?: InjuryReferral;
  estimated_days_out?: number | null;
  fitness_return_date?: string | null;
}

export function completeInjury(id: number, input: InjuryCompleteInput) {
  return apiPatch<InjuryDetail>(`/medical/injuries/${id}/complete/`, input);
}

export function addInjuryFollowUp(
  id: number,
  input: { entry_date: string; note: string; fitness_return_date?: string | null },
) {
  return apiPost<InjuryFollowUp>(`/medical/injuries/${id}/followups/`, input);
}

export function declareInjuryReturn(id: number, input: { return_date: string }) {
  return apiPost<InjuryDetail>(`/medical/injuries/${id}/return/`, input);
}

// ---------------------------------------------------------------------------
// Page « Médical » (§3)
// ---------------------------------------------------------------------------

export function listInjuriesToComplete(params: { limit?: number; offset?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<{ results: InjuryListItem[]; next_offset: number | null }>(
    `/medical/page/to-complete/${suffix}`,
  );
}

export function listRecentInjuries() {
  return apiGet<{ results: InjuryListItem[] }>("/medical/page/recent-injuries/");
}

export function listUnfitAndRestricted() {
  return apiGet<{ results: FitnessListItem[] }>("/medical/page/unfit/");
}
