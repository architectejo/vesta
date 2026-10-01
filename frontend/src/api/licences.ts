/**
 * Appels de l'app `licences` (CDC 2.5, 4.18, 5.4 ; tâche 1.9). Réservés au
 * Superuser côté API (`IsSuperuser`). Contrats lus directement dans
 * `backend/apps/licences/{urls,views,serializers}.py`.
 */

import { apiGet, apiPost } from "./client";

export interface Licence {
  id: number;
  club_id: number;
  club_name: string;
  status: "trial" | "active" | "expired" | "suspended" | "terminated";
  status_label: string;
  start_date: string;
  end_date: string;
  grace_period_days: number;
  created_by_id: number | null;
  created_at: string;
}

export function listLicences(params: { club_id?: number; status?: string } = {}) {
  const search = new URLSearchParams();
  if (params.club_id != null) search.set("club_id", String(params.club_id));
  if (params.status) search.set("status", params.status);
  const qs = search.toString();
  return apiGet<Licence[]>(`/licences/${qs ? `?${qs}` : ""}`);
}

export function getLicence(licenceId: number) {
  return apiGet<Licence>(`/licences/${licenceId}/`);
}

export interface LicenceEvent {
  id: number;
  licence_id: number;
  event_type: string;
  event_type_label: string;
  event_date: string;
  actor_id: number | null;
  note: string;
}

export function listLicenceEvents(licenceId: number) {
  return apiGet<LicenceEvent[]>(`/licences/${licenceId}/events/`);
}

export function activateLicence(
  licenceId: number,
  params: { start_date?: string | null; end_date?: string | null; note?: string },
) {
  return apiPost<Licence>(`/licences/${licenceId}/activate/`, params);
}

export function extendLicence(
  licenceId: number,
  params: { end_date: string; start_date?: string | null; note?: string },
) {
  return apiPost<Licence>(`/licences/${licenceId}/extend/`, params);
}

export function suspendLicence(licenceId: number, reason: string) {
  return apiPost<Licence>(`/licences/${licenceId}/suspend/`, { reason });
}

export function resumeLicence(licenceId: number, note?: string) {
  return apiPost<Licence>(`/licences/${licenceId}/resume/`, { note });
}

export function terminateLicence(
  licenceId: number,
  params: { reason: string; confirm_club_name: string },
) {
  return apiPost<Licence>(`/licences/${licenceId}/terminate/`, params);
}

export interface SupportSession {
  id: number;
  club_id: number;
  club_name: string;
  superuser_id: number;
  reason: string;
  started_at: string;
  expires_at: string;
  ended_at: string | null;
  is_valid: boolean;
}

export function listSupportSessions(params: { club_id?: number } = {}) {
  const search = new URLSearchParams();
  if (params.club_id != null) search.set("club_id", String(params.club_id));
  const qs = search.toString();
  return apiGet<SupportSession[]>(`/licences/support-sessions/${qs ? `?${qs}` : ""}`);
}

export function startSupportSession(params: { club_id: number; reason: string }) {
  return apiPost<SupportSession>("/licences/support-sessions/start/", params);
}

export function endSupportSession(sessionId: number) {
  return apiPost<SupportSession>(`/licences/support-sessions/${sessionId}/end/`);
}
