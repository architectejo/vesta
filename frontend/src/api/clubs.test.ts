import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearSessionTokens, setSessionTokens } from "../auth/session";
import { listClubPlayers, searchActiveClubPlayers, toPlayerSearchResult } from "./clubs";
import type { ClubPlayerListItem } from "./clubs";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const JONATHAN: ClubPlayerListItem = {
  membership_id: 42,
  first_name: "Jonathan",
  last_name: "Mbala",
  photo: "https://example.test/media/photos/xxx.jpg",
  position: "midfielder",
  position_label: "Milieu",
  position_detail: "",
  jersey_number: 8,
  membership_status: "active",
  membership_status_label: "Inscrit",
  roles: [{ role: "coach", label: "Coach" }],
};

describe("listClubPlayers", () => {
  beforeEach(beforeEachAuth);

  afterEach(() => {
    clearSessionTokens();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("n'ajoute aucun paramètre de requête quand aucun filtre n'est fourni", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, [JONATHAN]));
    vi.stubGlobal("fetch", fetchMock);

    await listClubPlayers();

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toMatch(/\/clubs\/players\/$/);
  });

  it("transmet search, position, status et role en paramètres de requête", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, [JONATHAN]));
    vi.stubGlobal("fetch", fetchMock);

    await listClubPlayers({ search: "Jon", position: "midfielder", status: "active", role: "coach" });

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("search=Jon");
    expect(url).toContain("position=midfielder");
    expect(url).toContain("status=active");
    expect(url).toContain("role=coach");
  });
});

describe("toPlayerSearchResult", () => {
  it("adapte un élément de l'effectif au format PlayerSearch, sans inventer de champ", () => {
    expect(toPlayerSearchResult(JONATHAN)).toEqual({
      id: 42,
      firstName: "Jonathan",
      lastName: "Mbala",
      number: 8,
      position: "Milieu",
      photoUrl: "https://example.test/media/photos/xxx.jpg",
    });
  });
});

describe("searchActiveClubPlayers", () => {
  beforeEach(beforeEachAuth);

  afterEach(() => {
    clearSessionTokens();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("force status=active quel que soit l'appelant (parrain, rôle, présidence, recruteurs)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, [JONATHAN]));
    vi.stubGlobal("fetch", fetchMock);

    const results = await searchActiveClubPlayers("Jon");

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("status=active");
    expect(url).toContain("search=Jon");
    expect(results).toEqual([toPlayerSearchResult(JONATHAN)]);
  });
});

function beforeEachAuth(): void {
  // Chaque bloc a besoin d'un jeton en session pour que `apiGet` ajoute
  // l'en-tête d'autorisation (comportement déjà couvert par client.test.ts).
  setSessionTokens({ access: "access-1", refresh: "refresh-1" });
}
