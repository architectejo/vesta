/**
 * Appels de l'app `accounts` (CDC 4.1, 7.1, 7.5). Contrats lus directement
 * dans `backend/apps/accounts/{urls,views,serializers}.py` (tâche 1.9) :
 * aucune forme de réponse n'est devinée.
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export interface UserSummary {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  is_superuser: boolean;
  must_change_password: boolean;
  preferred_theme: string;
}

export interface ClubSummary {
  id: number;
  slug: string;
  name: string;
  logo: string | null;
  primary_color: string;
  secondary_color: string;
}

export interface LoginSuccess {
  access: string;
  refresh: string;
  user: UserSummary;
  club: ClubSummary | null;
  must_change_password: boolean;
  terms_acceptance_required: boolean;
}

export function login(params: { email: string; password: string; club_slug?: string }) {
  return apiPost<LoginSuccess>("/auth/login/", params, { auth: false });
}

export function logout(refresh: string) {
  return apiPost<void>("/auth/logout/", { refresh });
}

export function logoutAllDevices() {
  return apiPost<{ tokens_blacklisted: number }>("/auth/logout-all/");
}

export function forcedPasswordChange(params: { new_password: string; confirm_password: string }) {
  return apiPost<{ detail: string }>("/auth/password/change/", params);
}

export function requestPasswordReset(email: string) {
  return apiPost<{ detail: string }>("/auth/password/reset-request/", { email }, { auth: false });
}

export function superuserResetPassword(email: string) {
  return apiPost<{ temporary_password: string }>("/auth/password/reset/", { email });
}

export interface AccountClubMembership {
  club_id: number;
  club_name: string;
  membership_status: string;
  roles: string[];
}

export interface AccountSearchResult {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_superuser: boolean;
  clubs: AccountClubMembership[];
}

export function searchAccounts(params: { query?: string; club_id?: number | null; role?: string }) {
  const search = new URLSearchParams();
  if (params.query) search.set("query", params.query);
  if (params.club_id != null) search.set("club_id", String(params.club_id));
  if (params.role) search.set("role", params.role);
  const qs = search.toString();
  return apiGet<AccountSearchResult[]>(`/auth/superuser/accounts/${qs ? `?${qs}` : ""}`);
}

export function deactivateAccount(params: { user_id: number; reason?: string }) {
  return apiPost<{ detail: string }>("/auth/superuser/accounts/deactivate/", params);
}

export interface PendingPasswordResetRequest {
  id: number;
  user_id: number;
  user_email: string;
  user_first_name: string;
  user_last_name: string;
  requested_at: string;
  status: string;
}

export function listPendingPasswordResets() {
  return apiGet<PendingPasswordResetRequest[]>("/auth/superuser/password-resets/pending/");
}

export interface TermsVersion {
  id: number;
  version_number: string;
  published_at: string;
  content: string;
}

export function getPendingTerms() {
  return apiGet<TermsVersion | null>("/auth/terms/pending/");
}

export function acceptTerms(termsVersionId: number) {
  return apiPost<{ terms_version_id: number; accepted_at: string }>("/auth/terms/accept/", {
    terms_version_id: termsVersionId,
  });
}

export interface PersonalInfoUpdateInput {
  first_name: string;
  last_name: string;
  phone?: string;
  birth_date?: string | null;
  weight_kg?: number | null;
  height_cm?: number | null;
}

export function updatePersonalInfo(input: PersonalInfoUpdateInput) {
  return apiPatch<{ detail: string }>("/auth/profile/personal-info/", input);
}

export interface CredentialsUpdateInput {
  email: string;
  current_password: string;
  new_password?: string;
  confirm_new_password?: string;
}

export function updateCredentials(input: CredentialsUpdateInput) {
  return apiPatch<{ detail: string }>("/auth/profile/credentials/", input);
}

export interface PinUpdateInput {
  current_password: string;
  new_pin: string;
  confirm_new_pin: string;
}

export function updatePin(input: PinUpdateInput) {
  return apiPost<{ detail: string }>("/auth/profile/pin/", input);
}

export function updateProfilePhoto(photo: File) {
  const form = new FormData();
  form.append("photo", photo);
  return apiPatch<{ detail: string }>("/auth/profile/photo/", form);
}

export function removeProfilePhoto() {
  return apiDelete<void>("/auth/profile/photo/");
}
