/**
 * Appels de l'app `notifications` utilisés à la tâche 1.9 (CDC 4.17) :
 * seule la préférence email est consommée par les écrans de ce lot
 * (`comptes-mon-profil.md` §3.8). Le reste de l'app (icône cloche, liste
 * des notifications) est hors périmètre de cette tâche.
 */

import { apiGet, apiPatch } from "./client";

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
