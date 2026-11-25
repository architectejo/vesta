import { describe, expect, it } from "vitest";
import { CATEGORY_FILTERS, CATEGORY_LABELS } from "./archivesFormat";

// Clés exactes de ArchivedDocument.Category côté API (backend/apps/assemblies/models.py).
const API_KEYS = ["pv_reunion", "convocation", "autre"];

describe("catégories de l'archive", () => {
  it("les libellés et filtres utilisent exactement les clés de l'API", () => {
    expect(Object.keys(CATEGORY_LABELS).sort()).toEqual([...API_KEYS].sort());
    expect(CATEGORY_FILTERS.map((f) => f.value).filter(Boolean).sort()).toEqual([...API_KEYS].sort());
    for (const key of API_KEYS) {
      expect(CATEGORY_LABELS[key as keyof typeof CATEGORY_LABELS]).toBeTruthy();
    }
  });
});
