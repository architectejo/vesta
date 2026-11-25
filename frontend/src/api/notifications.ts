/**
 * Appels de l'app `notifications` (CDC 3.4, 4.17).
 *
 * - La préférence email (`getNotificationPreference`/`setNotificationPreference`)
 *   est consommée par l'onglet « Informations » de la modale Mon profil
 *   (tâche 1.9, `comptes-mon-profil.md` §3.8).
 * - La liste, le compteur de non-lues et les deux actions de marquage
 *   (`getNotifications`, `getUnreadCount`, `markNotificationRead`,
 *   `markAllNotificationsRead`) alimentent l'icône cloche de la barre
 *   latérale (`design-system/components/NotificationBell.tsx` et
 *   `layouts/NotificationBellWidget.tsx`).
 */

import { apiGet, apiPatch, apiPost } from "./client";

export interface NotificationPreference {
  email_enabled: boolean;
  updated_at: string;
}

export function getNotificationPreference() {
  return apiGet<NotificationPreference>("/notifications/preference/");
}

export function setNotificationPreference(emailEnabled: boolean) {
  return apiPatch<NotificationPreference>("/notifications/preference/", {
    email_enabled: emailEnabled,
  });
}

/**
 * Une notification telle que renvoyée par `NotificationSerializer`
 * (`backend/apps/notifications/serializers.py`). `link_object_type` est le
 * nom de la classe du modèle cible (ex. « Match », « TacticalPlan »), vide
 * si la notification ne mène à aucun élément particulier (CDC 4.17).
 */
export interface AppNotification {
  id: number;
  event_type: string;
  title: string;
  body: string;
  link_object_type: string;
  link_object_id: number | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

/** Réponse paginée de `NotificationListView` (`NotificationPagination`, page de 10 par défaut, 50 au maximum). */
export interface NotificationListResult {
  count: number;
  next: string | null;
  previous: string | null;
  results: AppNotification[];
}

/**
 * Une page de notifications du joueur connecté, les plus récentes d'abord
 * (« N derniers + Voir plus », CDC 3.4). Pagination par numéro de page
 * (10 par page) : « Voir plus » charge la page suivante, sans plafond
 * (agrandir `page_size` serait borné à 50 par l'API).
 */
export function getNotifications(page: number) {
  return apiGet<NotificationListResult>(`/notifications/?page=${page}&page_size=10`);
}

export function getUnreadCount() {
  return apiGet<{ unread_count: number }>("/notifications/unread-count/");
}

export function markNotificationRead(notificationId: number) {
  return apiPost<AppNotification>(`/notifications/${notificationId}/read/`);
}

export function markAllNotificationsRead() {
  return apiPost<{ updated: number }>("/notifications/read-all/");
}
