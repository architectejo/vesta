/**
 * Appels de l'app `audit` (CDC 5.5, 4.18). Lecture seule, réservés au
 * Superuser côté API. Contrats : GET uniquement.
 */

import { apiDownload, apiGet } from "./client";

export interface AuditLogLine {
  id: number;
  created_at: string;
  club_id: number | null;
  club_name: string | null;
  club_timezone: string | null;
  actor_id: number | null;
  actor_display: string;
  acted_as_ghost: boolean;
  support_session_id: number | null;
  action_type: string;
  object_type: string;
  object_id: string;
  is_alert: boolean;
}

export interface AuditLogDetail extends AuditLogLine {
  support_session: { id: number; reason: string } | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  medical_content_withheld: boolean;
  ip_address: string | null;
  user_agent: string;
  device: string;
}

export interface AuditLogPage {
  count: number;
  next: string | null;
  previous: string | null;
  results: AuditLogLine[];
}

export interface AuditLogFilters {
  club_id?: number | null;
  actor_id?: number | null;
  /** Répétable ; un suffixe `*` signifie « préfixe ». */
  action_type?: string[];
  date_from?: string;
  date_to?: string;
  alerts_only?: boolean;
}

export const AUDIT_PAGE_SIZE = 50;

function buildQuery(filters: AuditLogFilters, extra: Record<string, string> = {}): string {
  const search = new URLSearchParams();
  if (filters.club_id != null) search.set("club_id", String(filters.club_id));
  if (filters.actor_id != null) search.set("actor_id", String(filters.actor_id));
  for (const type of filters.action_type ?? []) search.append("action_type", type);
  if (filters.date_from) search.set("date_from", filters.date_from);
  if (filters.date_to) search.set("date_to", filters.date_to);
  if (filters.alerts_only) search.set("alerts_only", "true");
  for (const [key, value] of Object.entries(extra)) search.set(key, value);
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export function listAuditLogs(filters: AuditLogFilters, page = 1) {
  return apiGet<AuditLogPage>(
    `/audit/logs/${buildQuery(filters, { page: String(page), page_size: String(AUDIT_PAGE_SIZE) })}`,
  );
}

export function getAuditLog(id: number) {
  return apiGet<AuditLogDetail>(`/audit/logs/${id}/`);
}

export function listAuditActionTypes() {
  return apiGet<{ results: Array<{ action_type: string; is_alert: boolean }> }>("/audit/action-types/");
}

/** Export CSV des entrées filtrées, téléchargé avec le jeton d'authentification. */
export function exportAuditLogs(filters: AuditLogFilters) {
  return apiDownload(`/audit/logs/export/${buildQuery(filters)}`, "journal-activite.csv");
}
