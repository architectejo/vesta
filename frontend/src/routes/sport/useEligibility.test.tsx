import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, listEligibility: vi.fn() };
});

import { listEligibility } from "../../api/sport";
import { ELIGIBILITY_QUERY_KEY, useEligibility } from "./useEligibility";

let client = new QueryClient();

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useEligibility (GET /sport/eligibility/, §4.1 bis)", () => {
  afterEach(() => {
    vi.clearAllMocks();
    client.clear();
    client = new QueryClient();
  });

  it("indexe les résultats de l'API par adhésion, motif inchangé", async () => {
    vi.mocked(listEligibility).mockResolvedValue({
      count: 2,
      results: [
        { membership_id: 13, eligible: false, reason_code: "pending_membership", reason: "En attente d'adhésion." },
        { membership_id: 14, eligible: true, reason_code: "", reason: "" },
      ],
    });
    const { result } = renderHook(() => useEligibility(true), { wrapper });

    await waitFor(() => expect(result.current.size).toBe(2));
    expect(result.current.get(13)?.reason).toBe("En attente d'adhésion.");
    expect(result.current.get(14)?.eligible).toBe(true);
  });

  it("n'appelle pas l'API quand la modale est fermée", () => {
    const { result } = renderHook(() => useEligibility(false), { wrapper });
    expect(listEligibility).not.toHaveBeenCalled();
    expect(result.current.size).toBe(0);
  });

  it("403 : table vide, sans nouvel essai", async () => {
    vi.mocked(listEligibility).mockRejectedValue(new ApiError(403, { detail: "Accès refusé." }));
    const { result } = renderHook(() => useEligibility(true), { wrapper });

    // Sans la règle « pas de nouvel essai sur 403 », la requête resterait en
    // cours (nouvel essai après 1 s) au lieu de passer tout de suite en erreur.
    await waitFor(() => expect(client.getQueryState(ELIGIBILITY_QUERY_KEY)?.status).toBe("error"), { timeout: 500 });
    expect(listEligibility).toHaveBeenCalledTimes(1);
    expect(result.current.size).toBe(0);
  });
});
