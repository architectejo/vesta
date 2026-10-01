/**
 * Client HTTP unique de l'interface Vesta (CLAUDE.md §7 : chaque endpoint
 * a un contrat déclaré côté API ; ce module ne fait qu'appeler ces
 * contrats, jamais n'en invente). Base URL configurable par variable
 * d'environnement (`VITE_API_URL`), jamais écrite en dur ailleurs dans le
 * code (CLAUDE.md §3.12 appliqué côté interface).
 */

import {
  clearSessionTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setSessionTokens,
} from "../auth/session";
import { getSupportSessionHeaderId } from "../auth/supportSession";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "/api/v1";

/**
 * Erreur HTTP normalisée. Les vues DRF de Vesta répondent soit
 * `{ detail, code?, ...contexte }` (erreurs métier, voir
 * `apps.accounts.views`/`apps.clubs.views`), soit un dictionnaire de champ
 * -> liste d'erreurs (sortie par défaut de `serializer.is_valid(raise_exception=True)`
 * quand la vue ne l'a pas interceptée). Cette classe distingue les deux
 * formes pour que chaque écran puisse afficher l'erreur au bon endroit
 * (CLAUDE.md §3 : jamais de code ni de message technique affiché).
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly detail: string;
  readonly fields: Record<string, string[]>;
  readonly raw: unknown;

  constructor(status: number, body: unknown) {
    let detail = "Une erreur est survenue de notre côté. Réessayez dans un instant.";
    let code: string | undefined;
    const fields: Record<string, string[]> = {};

    if (status === 0) {
      detail = "Connexion impossible. Vérifiez votre réseau et réessayez.";
    } else if (body && typeof body === "object" && !Array.isArray(body)) {
      const obj = body as Record<string, unknown>;
      if ("detail" in obj) {
        const rawDetail = obj.detail;
        detail = Array.isArray(rawDetail) ? rawDetail.map(String).join(" ") : String(rawDetail);
        if (typeof obj.code === "string") code = obj.code;
      } else {
        for (const [key, value] of Object.entries(obj)) {
          fields[key] = Array.isArray(value) ? value.map(String) : [String(value)];
        }
        const firstField = Object.values(fields)[0];
        if (firstField?.[0]) detail = firstField[0];
      }
    } else if (Array.isArray(body)) {
      detail = body.map(String).join(" ");
    } else if (status === 403) {
      detail = "Vous n'avez pas accès à cette action.";
    } else if (status === 404) {
      detail = "Cet élément n'existe plus.";
    } else if (status === 401) {
      detail = "Votre session a expiré. Reconnectez-vous.";
    }

    super(detail);
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.fields = fields;
    this.raw = body;
  }

  /** Premier message d'erreur pour un champ donné, s'il existe. */
  fieldError(name: string): string | undefined {
    return this.fields[name]?.[0];
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  /** `false` pour les points d'accès publics (connexion, création de club…). */
  auth?: boolean;
  signal?: AbortSignal;
}

async function rawRequest<T>(
  path: string,
  options: RequestOptions,
  accessOverride?: string | null,
): Promise<T> {
  const headers: Record<string, string> = {};
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;

  if (!isFormData && options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const useAuth = options.auth !== false;
  const token = accessOverride !== undefined ? accessOverride : useAuth ? getAccessToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  const supportSession = getSupportSessionHeaderId();
  if (supportSession && useAuth) headers["X-Support-Session"] = supportSession;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: isFormData
        ? (options.body as FormData)
        : options.body !== undefined
          ? JSON.stringify(options.body)
          : undefined,
      signal: options.signal,
    });
  } catch {
    throw new ApiError(0, null);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, data);
  }

  return data as T;
}

let refreshPromise: Promise<string | null> | null = null;

/**
 * Un seul appel de renouvellement en vol à la fois (CDC 7.1).
 *
 * Le back-end a `ROTATE_REFRESH_TOKENS = True` et
 * `BLACKLIST_AFTER_ROTATION = True` (`backend/config/settings/base.py`) :
 * chaque appel à `/auth/token/refresh/` renvoie donc un **nouveau** jeton de
 * rafraîchissement et met la liste noire sur l'ancien. Si l'interface ne
 * conserve pas ce nouveau jeton, le renouvellement suivant réutilise l'ancien
 * (déjà black-listé), échoue, et déconnecte l'utilisateur — après une seule
 * rotation, donc environ deux fois la durée de vie du jeton d'accès (15 min
 * + 15 min ≈ 30 min), même si le jeton de rafraîchissement de 7 jours est
 * encore largement valide. C'était la cause de la déconnexion prématurée
 * signalée par l'utilisateur : corrigé en persistant systématiquement le
 * couple access/refresh renvoyé par l'API plutôt que le seul jeton d'accès.
 */
function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return Promise.resolve(null);

  if (!refreshPromise) {
    refreshPromise = rawRequest<{ access: string; refresh?: string }>(
      "/auth/token/refresh/",
      { method: "POST", body: { refresh }, auth: false },
      null,
    )
      .then((result) => {
        if (result.refresh) {
          setSessionTokens({ access: result.access, refresh: result.refresh });
        } else {
          // Filet de sécurité si la rotation est un jour désactivée côté API :
          // seul le jeton d'accès change, l'ancien jeton de rafraîchissement reste valide.
          setAccessToken(result.access);
        }
        return result.access;
      })
      .catch(() => {
        clearSessionTokens();
        return null;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

/**
 * Appel API générique. Sur un 401 avec un jeton d'accès présent, tente un
 * seul renouvellement (jeton de 15 minutes, CDC 7.1) avant d'abandonner.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  try {
    return await rawRequest<T>(path, options);
  } catch (error) {
    const shouldRetry =
      error instanceof ApiError &&
      error.status === 401 &&
      options.auth !== false &&
      getAccessToken() !== null;
    if (!shouldRetry) throw error;

    const newAccess = await refreshAccessToken();
    if (!newAccess) throw error;
    return rawRequest<T>(path, options, newAccess);
  }
}

export function apiGet<T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}) {
  return apiRequest<T>(path, { ...options, method: "GET" });
}

export function apiPost<T>(
  path: string,
  body?: unknown,
  options: Omit<RequestOptions, "method" | "body"> = {},
) {
  return apiRequest<T>(path, { ...options, method: "POST", body });
}

export function apiPut<T>(
  path: string,
  body?: unknown,
  options: Omit<RequestOptions, "method" | "body"> = {},
) {
  return apiRequest<T>(path, { ...options, method: "PUT", body });
}

export function apiPatch<T>(
  path: string,
  body?: unknown,
  options: Omit<RequestOptions, "method" | "body"> = {},
) {
  return apiRequest<T>(path, { ...options, method: "PATCH", body });
}

export function apiDelete<T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}) {
  return apiRequest<T>(path, { ...options, method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Téléchargement de fichier authentifié (ex. export CSV de la grille des
// cotisations, CDC 4.4.7). Contrairement à `apiGet`, la réponse n'est pas du
// JSON : le corps est lu en `Blob` et le nom de fichier vient de l'en-tête
// `Content-Disposition` envoyé par l'API (jamais recalculé côté interface,
// pour ne pas dupliquer la règle de nommage du serveur).
// ---------------------------------------------------------------------------

export interface DownloadResult {
  blob: Blob;
  filename: string;
}

function filenameFromContentDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const match = /filename="?([^";]+)"?/i.exec(header);
  return match?.[1] ?? fallback;
}

async function fetchDownload(path: string, token: string | null): Promise<Response> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const supportSession = getSupportSessionHeaderId();
  if (supportSession) headers["X-Support-Session"] = supportSession;
  try {
    return await fetch(`${API_BASE_URL}${path}`, { method: "GET", headers });
  } catch {
    throw new ApiError(0, null);
  }
}

/** Un seul renouvellement de jeton tenté sur un 401, comme `apiRequest`. */
export async function apiDownload(path: string, fallbackFilename: string): Promise<DownloadResult> {
  let response = await fetchDownload(path, getAccessToken());
  if (response.status === 401) {
    const newAccess = await refreshAccessToken();
    if (newAccess) response = await fetchDownload(path, newAccess);
  }
  if (!response.ok) {
    const text = await response.text();
    let data: unknown = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }
    throw new ApiError(response.status, data);
  }
  const blob = await response.blob();
  const filename = filenameFromContentDisposition(response.headers.get("Content-Disposition"), fallbackFilename);
  return { blob, filename };
}

/** Déclenche le téléchargement navigateur d'un `Blob` déjà récupéré. */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
