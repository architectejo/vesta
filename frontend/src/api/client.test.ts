import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearSessionTokens, getRefreshToken, setSessionTokens } from "../auth/session";
import { ApiError, apiGet, apiPost } from "./client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ApiError", () => {
  it("lit le message d'une erreur métier { detail, code }", () => {
    const error = new ApiError(401, { code: "invalid_credentials", detail: "Email ou mot de passe incorrect." });
    expect(error.detail).toBe("Email ou mot de passe incorrect.");
    expect(error.code).toBe("invalid_credentials");
    expect(error.fields).toEqual({});
  });

  it("lit les erreurs de champ d'un serializer DRF", () => {
    const error = new ApiError(400, { email: ["Saisissez une adresse email valide."] });
    expect(error.fieldError("email")).toBe("Saisissez une adresse email valide.");
    expect(error.detail).toBe("Saisissez une adresse email valide.");
  });

  it("utilise un message générique pour une panne réseau", () => {
    const error = new ApiError(0, null);
    expect(error.detail).toBe("Connexion impossible. Vérifiez votre réseau et réessayez.");
  });
});

describe("apiRequest", () => {
  beforeEach(() => {
    setSessionTokens({ access: "access-1", refresh: "refresh-1" });
  });

  afterEach(() => {
    clearSessionTokens();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("envoie le jeton d'accès et renvoie le JSON reçu", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { detail: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiGet<{ detail: string }>("/clubs/profile/me/");

    expect(result).toEqual({ detail: "ok" });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access-1");
  });

  it("refuse un statut 200 qui n'est pas du JSON (page index.html renvoyée par le repli du .htaccess)", async () => {
    // Non-régression (production, 13/10/2026) : sans VITE_API_URL, la connexion
    // appelait /api/v1 sur le domaine de l'interface ; le .htaccess répondait
    // par index.html en 200, pris à tort pour une connexion réussie.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<!doctype html><html><body>Vesta</body></html>", {
          status: 200,
          headers: { "Content-Type": "text/html" },
        }),
      ),
    );

    await expect(apiPost("/auth/login/", { email: "a@b.cd", password: "x" }, { auth: false })).rejects.toMatchObject({
      status: 502,
      detail: "Le serveur a répondu de façon inattendue. Réessayez, ou contactez le support si cela continue.",
    });
  });

  it("renouvelle le jeton une fois sur un 401 puis rejoue la requête", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: "Votre session a expiré." }))
      .mockResolvedValueOnce(jsonResponse(200, { access: "access-2" }))
      .mockResolvedValueOnce(jsonResponse(200, { detail: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiGet<{ detail: string }>("/clubs/profile/me/");

    expect(result).toEqual({ detail: "ok" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const lastCall = fetchMock.mock.calls[2] as [string, RequestInit];
    expect((lastCall[1].headers as Record<string, string>).Authorization).toBe("Bearer access-2");
  });

  it("persiste le nouveau jeton de rafraîchissement renvoyé par la rotation (SIMPLE_JWT ROTATE_REFRESH_TOKENS)", async () => {
    // Non-régression : le back-end (`ROTATE_REFRESH_TOKENS = True`,
    // `BLACKLIST_AFTER_ROTATION = True`) met l'ancien jeton de rafraîchissement
    // en liste noire à chaque rotation. Si l'interface ne persistait que le
    // jeton d'accès (bug d'origine), le renouvellement suivant réutilisait le
    // jeton déjà black-listé et déconnectait l'utilisateur au bout d'environ
    // 30 minutes au lieu des 7 jours prévus (CDC 7.1).
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: "Votre session a expiré." }))
      .mockResolvedValueOnce(jsonResponse(200, { access: "access-2", refresh: "refresh-2" }))
      .mockResolvedValueOnce(jsonResponse(200, { detail: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await apiGet<{ detail: string }>("/clubs/profile/me/");

    expect(getRefreshToken()).toBe("refresh-2");
  });

  it("propage l'erreur si le renouvellement échoue aussi", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: "expiré" }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: "refresh invalide" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiPost("/auth/logout/", {})).rejects.toBeInstanceOf(ApiError);
  });
});
