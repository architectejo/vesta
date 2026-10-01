/**
 * Appels de l'app `social` (CDC 4.16 ; docs/ecrans/fil-public-communication.md).
 * Contrats lus directement dans `backend/apps/social/{urls,views,serializers}.py`.
 *
 * Point de sécurité critique (rappel) : une image de publication « Club »
 * et toute image de chat (canal Général compris) ne sont JAMAIS sur un
 * chemin `MEDIA_URL` public. Le champ `url`/`image_url` renvoyé par l'API
 * est soit une adresse absolue (publication « Publique »), soit un chemin
 * relatif de la vue de téléchargement authentifiée : dans ce dernier cas,
 * on ignore ce texte et on reconstruit l'appel depuis l'identifiant
 * (`downloadPostImage`/`downloadAnnouncementImage`/`downloadChatMessageImage`),
 * exactement comme les pièces jointes de trésorerie (`api/treasury.ts`).
 */

import { apiDelete, apiDownload, apiGet, apiPatch, apiPost, type DownloadResult } from "./client";

export interface AuthorSummary {
  id: number;
  first_name: string;
  last_name: string;
  avatar_url: string | null;
}

// ---------------------------------------------------------------------------
// Fil d'actualité (PARTIE A)
// ---------------------------------------------------------------------------

export type PostVisibility = "public" | "club_only";
export type PostKind = "manual" | "auto_result" | "auto_transfer" | "auto_new_player";

export interface PostImage {
  id: number;
  order: number;
  /** Adresse absolue (visibilité Publique) ou chemin privé à ignorer (voir docstring). */
  url: string | null;
}

export interface Comment {
  id: number;
  post_id: number;
  author: AuthorSummary;
  body: string;
  created_at: string;
}

export interface Post {
  id: number;
  author: AuthorSummary;
  club_id: number;
  club_name: string;
  body: string;
  visibility: PostVisibility;
  post_kind: PostKind;
  created_at: string;
  images: PostImage[];
  like_count: number;
  comment_count: number;
  is_liked_by_me: boolean;
  recent_comments: Comment[];
  can_delete: boolean;
  is_reported_by_me: boolean;
}

export interface PostListResponse {
  results: Post[];
  count: number;
  next_offset: number | null;
}

export type PostScope = "mon_club" | "tous";

export function listPosts(params: { portee?: PostScope; limit?: number; offset?: number } = {}) {
  const query = new URLSearchParams();
  if (params.portee) query.set("portee", params.portee);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString();
  return apiGet<PostListResponse>(`/social/posts/${suffix ? `?${suffix}` : ""}`);
}

export interface PostCreateInput {
  body: string;
  visibility: PostVisibility;
  images: File[];
}

function toPostFormData(input: PostCreateInput): FormData {
  const form = new FormData();
  form.append("body", input.body);
  form.append("visibility", input.visibility);
  for (const image of input.images) form.append("images", image);
  return form;
}

export function createPost(input: PostCreateInput) {
  return apiPost<Post>("/social/posts/", toPostFormData(input));
}

export function getPost(id: number) {
  return apiGet<Post>(`/social/posts/${id}/`);
}

export function deletePost(id: number) {
  return apiDelete(`/social/posts/${id}/delete/`);
}

export function togglePostLike(id: number) {
  return apiPost<{ liked: boolean; like_count: number }>(`/social/posts/${id}/like/`);
}

export interface CommentListResponse {
  results: Comment[];
  count: number;
  next_offset: number | null;
}

export function listComments(postId: number, params: { limit?: number; offset?: number } = {}) {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString();
  return apiGet<CommentListResponse>(`/social/posts/${postId}/comments/${suffix ? `?${suffix}` : ""}`);
}

export function addComment(postId: number, body: string) {
  return apiPost<Comment>(`/social/posts/${postId}/comments/`, { body });
}

export function deleteComment(commentId: number) {
  return apiDelete(`/social/comments/${commentId}/`);
}

export function reportPost(postId: number, reason: string) {
  return apiPost<{ detail: string }>(`/social/posts/${postId}/report/`, { reason });
}

export function downloadPostImage(imageId: number): Promise<DownloadResult> {
  return apiDownload(`/social/post-images/${imageId}/`, `image-publication-${imageId}`);
}

// ---------------------------------------------------------------------------
// Communiqués (PARTIE B)
// ---------------------------------------------------------------------------

export interface AnnouncementImage {
  id: number;
  order: number;
  url: string | null;
}

export interface AnnouncementReadSummary {
  read_count: number;
  total: number;
}

export interface Announcement {
  id: number;
  title: string;
  body: string;
  published_by: AuthorSummary;
  published_at: string;
  pinned: boolean;
  expires_at: string | null;
  images: AnnouncementImage[];
  is_read_by_me: boolean;
  read_summary: AnnouncementReadSummary | null;
}

export interface AnnouncementListResponse {
  results: Announcement[];
  count: number;
  next_offset: number | null;
}

export function listAnnouncements(
  params: { pinned?: boolean; limit?: number; offset?: number } = {},
) {
  const query = new URLSearchParams();
  if (params.pinned) query.set("pinned", "true");
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString();
  return apiGet<AnnouncementListResponse>(`/social/announcements/${suffix ? `?${suffix}` : ""}`);
}

export interface AnnouncementCreateInput {
  title: string;
  body: string;
  images: File[];
  pinned: boolean;
}

function toAnnouncementFormData(input: AnnouncementCreateInput): FormData {
  const form = new FormData();
  form.append("title", input.title);
  form.append("body", input.body);
  form.append("pinned", String(input.pinned));
  for (const image of input.images) form.append("images", image);
  return form;
}

export function createAnnouncement(input: AnnouncementCreateInput) {
  return apiPost<Announcement>("/social/announcements/", toAnnouncementFormData(input));
}

export function getAnnouncement(id: number) {
  return apiGet<Announcement>(`/social/announcements/${id}/`);
}

export function markAnnouncementRead(id: number) {
  return apiPost<{ detail: string }>(`/social/announcements/${id}/read/`);
}

export function setAnnouncementPinned(id: number, pinned: boolean) {
  return apiPatch<{ pinned: boolean }>(`/social/announcements/${id}/pin/`, { pinned });
}

export interface AnnouncementReadReceiptRow {
  membership_id: number;
  first_name: string;
  last_name: string;
  read: boolean;
}

export function getAnnouncementReadReceipts(id: number, filter: "read" | "unread") {
  return apiGet<{ results: AnnouncementReadReceiptRow[] } & AnnouncementReadSummary>(
    `/social/announcements/${id}/read-receipts/?filter=${filter}`,
  );
}

export function downloadAnnouncementImage(imageId: number): Promise<DownloadResult> {
  return apiDownload(`/social/announcement-images/${imageId}/`, `image-communique-${imageId}`);
}

// ---------------------------------------------------------------------------
// Chat d'équipe (PARTIE C)
// ---------------------------------------------------------------------------

export type ChatChannelType = "general" | "board";

export interface ChatMessage {
  id: number;
  channel_id: number;
  sender: AuthorSummary;
  body: string;
  image_url: string | null;
  sent_at: string;
}

export interface ChatChannel {
  id: number;
  channel_type: ChatChannelType;
  unread_count: number;
  last_message: ChatMessage | null;
}

export function listChatChannels() {
  return apiGet<{ results: ChatChannel[] }>("/social/chat/channels/");
}

export interface ChatMessageListResponse {
  results: ChatMessage[];
  count: number;
  next_offset: number | null;
}

export function listChatMessages(
  channelId: number,
  params: { limit?: number; offset?: number; after?: number } = {},
) {
  const query = new URLSearchParams();
  if (params.after !== undefined) query.set("after", String(params.after));
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.offset !== undefined) query.set("offset", String(params.offset));
  const suffix = query.toString();
  return apiGet<ChatMessageListResponse>(`/social/chat/channels/${channelId}/messages/${suffix ? `?${suffix}` : ""}`);
}

export function sendChatMessage(channelId: number, input: { body: string; image?: File | null }) {
  const form = new FormData();
  form.append("body", input.body);
  if (input.image) form.append("image", input.image);
  return apiPost<ChatMessage>(`/social/chat/channels/${channelId}/messages/`, form);
}

export function markChannelRead(channelId: number, lastReadMessageId?: number) {
  return apiPost<{ detail: string }>(`/social/chat/channels/${channelId}/read/`, {
    last_read_message_id: lastReadMessageId,
  });
}

export function downloadChatMessageImage(messageId: number): Promise<DownloadResult> {
  return apiDownload(`/social/chat/messages/${messageId}/image/`, `image-message-${messageId}`);
}
