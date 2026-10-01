/**
 * Jeton de session de CET onglet (CDC 7.4, CLAUDE.md §2.7 : « Session
 * propre à chaque onglet »). `sessionStorage` est déjà, par nature, isolé
 * par onglet (contrairement à `localStorage`, partagé entre onglets d'une
 * même origine) : c'est le mécanisme retenu pour cette raison précise,
 * pas seulement par commodité.
 *
 * Module séparé de `api/client.ts` pour éviter tout import circulaire entre
 * la couche HTTP et le contexte React d'authentification (`AuthContext`).
 */

const ACCESS_KEY = "vesta:access";
const REFRESH_KEY = "vesta:refresh";
const IDENTITY_KEY = "vesta:identity";

/**
 * Aucun point d'accès « qui suis-je ? » léger n'existe côté API (voir
 * `backend/apps/accounts/urls.py`) pour re-authentifier l'utilisateur d'un
 * onglet après un simple rechargement de page. À défaut, l'interface
 * conserve un instantané non sensible (identifiant, nom, club) de la
 * réponse de connexion dans `sessionStorage`, à côté des jetons : ni plus
 * ni moins exposé que le jeton d'accès déjà stocké au même endroit. Un
 * rechargement revérifie quand même l'état réel (mot de passe à changer,
 * CGU en attente) auprès de l'API dès que possible (voir `AuthProvider`) —
 * ce n'est qu'un point de départ d'affichage, jamais une source de vérité
 * pour une décision de sécurité.
 */
export interface StoredIdentity {
  user: {
    id: number;
    email: string;
    first_name: string;
    last_name: string;
    is_superuser: boolean;
    must_change_password: boolean;
    preferred_theme: string;
  };
  club: { id: number; slug: string; name: string; logo: string | null; primary_color: string; secondary_color: string } | null;
}

type Listener = () => void;
const listeners = new Set<Listener>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function subscribeToSession(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(REFRESH_KEY);
}

export function setSessionTokens(tokens: { access: string; refresh: string }): void {
  window.sessionStorage.setItem(ACCESS_KEY, tokens.access);
  window.sessionStorage.setItem(REFRESH_KEY, tokens.refresh);
  notify();
}

export function setAccessToken(access: string): void {
  window.sessionStorage.setItem(ACCESS_KEY, access);
  notify();
}

export function clearSessionTokens(): void {
  window.sessionStorage.removeItem(ACCESS_KEY);
  window.sessionStorage.removeItem(REFRESH_KEY);
  window.sessionStorage.removeItem(IDENTITY_KEY);
  notify();
}

export function hasSession(): boolean {
  return getAccessToken() !== null;
}

export function getStoredIdentity(): StoredIdentity | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(IDENTITY_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredIdentity;
  } catch {
    return null;
  }
}

export function setStoredIdentity(identity: StoredIdentity): void {
  window.sessionStorage.setItem(IDENTITY_KEY, JSON.stringify(identity));
  notify();
}
