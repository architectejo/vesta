/**
 * Session de support en Ghost Mode (CDC 4.18, 5.4 ; tâche 1.9,
 * `superuser-espace.md` §4.4). L'identifiant de la `SupportSession` démarrée
 * est transmis sur chaque requête via l'en-tête `X-Support-Session` (contrat
 * exact de `apps.core.authentication.TenantJWTAuthentication`, voir
 * `apps/core/authentication.py`). Stocké en mémoire de l'onglet
 * (`sessionStorage`, même raison qu'`auth/session.ts`) pour survivre à un
 * rechargement accidentel de la page pendant une intervention.
 */

const SUPPORT_SESSION_KEY = "vesta:support-session";

export interface ActiveSupportSession {
  id: string;
  clubId: number;
  clubName: string;
  reason: string;
  expiresAt: string;
}

type Listener = () => void;
const listeners = new Set<Listener>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function subscribeToSupportSession(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getSupportSessionHeaderId(): string | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(SUPPORT_SESSION_KEY);
  if (!raw) return null;
  try {
    return (JSON.parse(raw) as ActiveSupportSession).id;
  } catch {
    return null;
  }
}

export function getActiveSupportSession(): ActiveSupportSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(SUPPORT_SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ActiveSupportSession;
  } catch {
    return null;
  }
}

export function setActiveSupportSession(session: ActiveSupportSession | null): void {
  if (session) {
    window.sessionStorage.setItem(SUPPORT_SESSION_KEY, JSON.stringify(session));
  } else {
    window.sessionStorage.removeItem(SUPPORT_SESSION_KEY);
  }
  notify();
}
