/**
 * Appels de l'app `mercato` (Lot 4, tâche 4.14 ; fiche `docs/ecrans/mercato.md`).
 * Contrats lus directement dans `backend/apps/mercato/{urls,views,serializers}.py` :
 * aucune forme n'est devinée ici. **Étanchéité (§2.1)** : les champs publics
 * d'un joueur d'un autre club sont ceux, et seulement ceux, renvoyés par
 * l'API (jamais complétés côté interface).
 */

import { apiDownload, apiGet, apiPatch, apiPost, type DownloadResult } from "./client";

export interface ClubBrief {
  id: number;
  name: string;
  logo: string | null;
}

export interface PublicPlayer {
  membership_id: number;
  first_name: string;
  last_name: string;
  photo: string | null;
  position: string;
  position_label: string;
  jersey_number: number | null;
  age: number | null;
  club: ClubBrief;
  average_rating: string | null;
  is_on_transfer_market: boolean;
}

export interface MarketRow extends PublicPlayer {
  is_own_club: boolean;
}

export interface ListMarketParams {
  position?: string;
  club?: number;
  search?: string;
}

export function getAvailability() {
  return apiGet<{ is_on_transfer_market: boolean }>("/mercato/availability/");
}

export function setAvailability(isOnMarket: boolean) {
  return apiPatch<{ is_on_transfer_market: boolean }>("/mercato/availability/", {
    is_on_transfer_market: isOnMarket,
  });
}

export function listMarket(params: ListMarketParams = {}) {
  const qs = new URLSearchParams();
  if (params.position) qs.set("position", params.position);
  if (params.club) qs.set("club", String(params.club));
  if (params.search) qs.set("search", params.search);
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiGet<{ count: number; results: MarketRow[] }>(`/mercato/market/${suffix}`);
}

export function getPublicPlayer(membershipId: number) {
  return apiGet<PublicPlayer>(`/mercato/players/${membershipId}/`);
}

// ---------------------------------------------------------------------------
// Offres de transfert
// ---------------------------------------------------------------------------

export type TransferOfferStatus =
  | "sent"
  | "accepted_by_player"
  | "declined_by_player"
  | "blocked_debt"
  | "awaiting_quitus"
  | "completed"
  | "cancelled";

export interface TransferOffer {
  id: number;
  status: TransferOfferStatus;
  origin_club: ClubBrief;
  target_club: ClubBrief;
  player: PublicPlayer;
  message: string;
  conditions: string;
  membership_fee_due_at_target: boolean;
  debt_amount: string | null;
  debt_checked_at: string | null;
  player_decision_at: string | null;
  quitus_available: boolean;
  completed_at: string | null;
  created_at: string;
}

export interface OfferCreateInput {
  target_membership_id: number;
  message: string;
  conditions?: string;
}

export function createOffer(input: OfferCreateInput) {
  return apiPost<TransferOffer>("/mercato/offers/", input);
}

export function listMyOffers() {
  return apiGet<{ count: number; results: TransferOffer[] }>("/mercato/offers/mine/");
}

export function listClubOffers(params: { direction: "sent" | "received"; status?: TransferOfferStatus }) {
  const qs = new URLSearchParams();
  qs.set("direction", params.direction);
  if (params.status) qs.set("status", params.status);
  return apiGet<{ count: number; results: TransferOffer[] }>(`/mercato/offers/club/?${qs}`);
}

export function getOffer(id: number) {
  return apiGet<TransferOffer>(`/mercato/offers/${id}/`);
}

export function respondOffer(id: number, accept: boolean) {
  return apiPost<TransferOffer>(`/mercato/offers/${id}/respond/`, { accept });
}

export function downloadQuitus(id: number): Promise<DownloadResult> {
  return apiDownload(`/mercato/offers/${id}/quitus/`, `quitus-${id}.pdf`);
}

// ---------------------------------------------------------------------------
// Messagerie entre clubs (Président/DS de chaque club seulement)
// ---------------------------------------------------------------------------

export interface MercatoThread {
  id: number;
  other_club: ClubBrief;
  subject: string;
  transfer_offer_id: number | null;
  unread_count: number;
  created_at: string;
}

export interface MercatoMessage {
  id: number;
  club_id: number;
  sender: { id: number; name: string };
  body: string;
  sent_at: string;
  read_at: string | null;
}

export function listThreads() {
  return apiGet<{ count: number; results: MercatoThread[] }>("/mercato/threads/");
}

export interface ThreadCreateInput {
  club_id: number;
  subject?: string;
  message: string;
  transfer_offer_id?: number | null;
}

export function createThread(input: ThreadCreateInput) {
  return apiPost<MercatoThread>("/mercato/threads/", input);
}

export function listThreadMessages(threadId: number) {
  return apiGet<{ results: MercatoMessage[] }>(`/mercato/threads/${threadId}/messages/`);
}

export function sendThreadMessage(threadId: number, body: string) {
  return apiPost<MercatoMessage>(`/mercato/threads/${threadId}/messages/`, { body });
}
