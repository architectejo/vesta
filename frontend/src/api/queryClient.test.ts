import { describe, expect, it } from "vitest";
import { ApiError } from "./client";
import { createQueryClient, shouldRetryQuery } from "./queryClient";

describe("shouldRetryQuery", () => {
  it("ne relance jamais un refus de permission (403)", () => {
    expect(shouldRetryQuery(0, new ApiError(403, { detail: "Interdit" }))).toBe(false);
  });

  it("relance une erreur réseau ou serveur jusqu'à 3 fois", () => {
    expect(shouldRetryQuery(0, new Error("réseau"))).toBe(true);
    expect(shouldRetryQuery(2, new ApiError(500, { detail: "Erreur" }))).toBe(true);
    expect(shouldRetryQuery(3, new Error("réseau"))).toBe(false);
  });

  it("est le réglage par défaut du client de requêtes", () => {
    expect(createQueryClient().getDefaultOptions().queries?.retry).toBe(shouldRetryQuery);
  });
});
