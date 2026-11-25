/**
 * Appels de l'app `assemblies` (CDC 4.15 ; docs/ecrans/assemblees-page-ag.md).
 * Contrats lus directement dans `backend/apps/assemblies/{urls,views,serializers}.py`.
 */

import { apiDelete, apiGet, apiPost, apiPut, apiDownload, type DownloadResult } from "./client";

export type AssemblyType = "ordinary" | "extraordinary";
export type AssemblyStatus = "scheduled" | "held" | "cancelled";

export interface AgendaItem {
  id: number;
  order: number;
  title: string;
  description: string;
}

export interface Decision {
  id: number;
  agenda_item_id: number;
  votes_for: number;
  votes_against: number;
  votes_abstain: number;
  outcome: string;
  linked_object_type: string;
  linked_object_id: number | null;
  recorded_by_name: string;
  recorded_at: string;
}

export interface Quorum {
  present: number;
  total: number;
  percentage: string;
  threshold: string;
  reached: boolean;
}

export interface Minutes {
  content: string;
  president_signed_by_name: string;
  president_signed_at: string | null;
  vp_signed_by_name: string;
  vp_signed_at: string | null;
  vp_vacant_at_signature: boolean;
  is_complete: boolean;
  generated_at: string | null;
  pdf_url: string | null;
}

export interface Assembly {
  id: number;
  assembly_type: AssemblyType;
  scheduled_date: string;
  scheduled_time: string;
  location: string;
  status: AssemblyStatus;
  created_at: string;
  agenda_items: AgendaItem[];
  decisions: Decision[];
  quorum: Quorum;
  minutes: Minutes | null;
  can_manage: boolean;
  /** Président, VP, Secrétaire (CDC 4.15, 10.3 n° 170) : décidé par l'API. */
  can_convene: boolean;
  can_sign_president: boolean;
  can_sign_vice_president: boolean;
}

export interface AssemblyListResponse {
  results: Assembly[];
  count: number;
  next_offset: number | null;
}

export function listAssemblies(
  params: { status?: "scheduled" | "held"; limit?: number; offset?: number } = {},
) {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString();
  return apiGet<AssemblyListResponse>(`/assemblies/${suffix ? `?${suffix}` : ""}`);
}

export interface ConveneAssemblyInput {
  assembly_type: AssemblyType;
  scheduled_date: string;
  scheduled_time: string;
  location?: string;
  agenda_items: Array<{ title: string; description?: string }>;
}

export function conveneAssembly(input: ConveneAssemblyInput) {
  return apiPost<Assembly>("/assemblies/", input);
}

export function getAssembly(id: number) {
  return apiGet<Assembly>(`/assemblies/${id}/`);
}

export interface AttendanceRow {
  membership_id: number;
  first_name: string;
  last_name: string;
  jersey_number: number | null;
  present: boolean;
}

export interface AttendanceListResponse {
  results: AttendanceRow[];
  counts: { all: number; present: number; unchecked: number };
}

export function listAttendance(
  assemblyId: number,
  params: { filter?: "all" | "present" | "unchecked"; q?: string } = {},
) {
  const query = new URLSearchParams();
  if (params.filter) query.set("filter", params.filter);
  if (params.q) query.set("q", params.q);
  const suffix = query.toString();
  return apiGet<AttendanceListResponse>(`/assemblies/${assemblyId}/attendance/${suffix ? `?${suffix}` : ""}`);
}

export function markAttendance(assemblyId: number, membershipId: number) {
  return apiPost(`/assemblies/${assemblyId}/attendance/`, { membership_id: membershipId });
}

export function removeAttendance(assemblyId: number, membershipId: number) {
  return apiDelete(`/assemblies/${assemblyId}/attendance/${membershipId}/`);
}

export interface DecisionInput {
  votes_for: number;
  votes_against: number;
  votes_abstain: number;
  outcome: string;
  linked_object_type?: string;
  linked_object_id?: number | null;
}

export function recordDecision(assemblyId: number, agendaItemId: number, input: DecisionInput) {
  return apiPut<Decision>(`/assemblies/${assemblyId}/agenda-items/${agendaItemId}/decision/`, input);
}

export function draftMinutes(assemblyId: number, content: string) {
  return apiPut<Minutes>(`/assemblies/${assemblyId}/minutes/`, { content });
}

export function signMinutes(assemblyId: number) {
  return apiPost<Minutes>(`/assemblies/${assemblyId}/minutes/sign/`, {});
}

export function downloadMinutesPdf(assemblyId: number): Promise<DownloadResult> {
  return apiDownload(`/assemblies/${assemblyId}/minutes/pdf/`, `pv-ag-${assemblyId}.pdf`);
}

export function getQuorumThreshold() {
  return apiGet<{ percentage: string }>("/assemblies/quorum-threshold/");
}

export function updateQuorumThreshold(percentage: number) {
  return apiPut<{ percentage: string }>("/assemblies/quorum-threshold/", { percentage });
}


// ---------------------------------------------------------------------------
// Archive des documents officiels (CDC 4.15.1 ; docs/ecrans/club-archives.md).
// ---------------------------------------------------------------------------

export type ArchiveCategory = "pv_reunion" | "convocation" | "autre";
export type ArchiveStatus = "active" | "withdrawn";

export interface ArchivedDocument {
  id: number;
  category: ArchiveCategory;
  category_label: string;
  title: string;
  document_date: string;
  status: ArchiveStatus;
  status_label: string;
  uploaded_by_name: string;
  uploaded_at: string;
  withdrawn_by_name: string;
  withdrawn_at: string | null;
  withdrawn_reason: string;
  replaces_id: number | null;
  replaced_by_id: number | null;
  file_name: string;
  file_size: number | null;
  download_url: string;
}

export interface ArchivedDocumentListResponse {
  results: ArchivedDocument[];
  count: number;
  next_offset: number | null;
}

export interface ListArchivedDocumentsParams {
  category?: ArchiveCategory;
  year?: string;
  includeWithdrawn?: boolean;
  limit?: number;
  offset?: number;
}

export function listArchivedDocuments(params: ListArchivedDocumentsParams = {}) {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.year) query.set("year", params.year);
  if (params.includeWithdrawn) query.set("include_withdrawn", "1");
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString();
  return apiGet<ArchivedDocumentListResponse>(`/assemblies/documents/${suffix ? `?${suffix}` : ""}`);
}

export function getArchivedDocument(id: number) {
  return apiGet<ArchivedDocument>(`/assemblies/documents/${id}/`);
}

export interface ArchivedDocumentInput {
  category: ArchiveCategory;
  title: string;
  document_date: string;
  file: File;
}

function toDocumentFormData(input: ArchivedDocumentInput): FormData {
  const form = new FormData();
  form.append("category", input.category);
  form.append("title", input.title);
  form.append("document_date", input.document_date);
  form.append("file", input.file);
  return form;
}

export function uploadArchivedDocument(input: ArchivedDocumentInput) {
  return apiPost<ArchivedDocument>("/assemblies/documents/", toDocumentFormData(input));
}

/** L'ancien document est retiré et conservé ; le nouveau le référence. */
export function replaceArchivedDocument(id: number, input: ArchivedDocumentInput) {
  return apiPost<ArchivedDocument>(`/assemblies/documents/${id}/replace/`, toDocumentFormData(input));
}

export function withdrawArchivedDocument(id: number, reason: string) {
  return apiPost<ArchivedDocument>(`/assemblies/documents/${id}/withdraw/`, { reason });
}

/** Téléchargement authentifié (CDC 6.7, règle n° 10) : jamais d'adresse publique. */
export function downloadArchivedDocument(id: number): Promise<DownloadResult> {
  return apiDownload(`/assemblies/documents/${id}/file/`, `archive-${id}`);
}
