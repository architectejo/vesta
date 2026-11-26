import { describe, expect, it } from "vitest";
import {
  articlesLabel,
  ALL_MOVEMENT_TYPE_OPTIONS,
  ARTICLE_CATEGORY_OPTIONS,
  IN_MOVEMENT_TYPE_OPTIONS,
  decommissionStatusKey,
  equipmentLineStatusKey,
  normalizeText,
  inventoryLineStatusKey,
  inventoryStatusKey,
} from "./materielLabels";

describe("equipmentLineStatusKey", () => {
  it("associe chaque statut d'équipement de match à la bonne clé de badge", () => {
    expect(equipmentLineStatusKey("out")).toBe("equipment_out");
    expect(equipmentLineStatusKey("partially_returned")).toBe("equipment_partially_returned");
    expect(equipmentLineStatusKey("returned")).toBe("equipment_returned");
  });
});

describe("inventoryStatusKey", () => {
  it("un inventaire clôturé est toujours « Clôturé », qu'il ait bloqué ou non", () => {
    expect(inventoryStatusKey("closed", true)).toBe("inventory_closed");
    expect(inventoryStatusKey("closed", false)).toBe("inventory_closed");
  });

  it("un inventaire ouvert non bloquant est « En cours »", () => {
    expect(inventoryStatusKey("open", false)).toBe("inventory_open");
  });

  it("un inventaire ouvert bloquant (trimestre suivant empêché) est « Non clôturé »", () => {
    expect(inventoryStatusKey("open", true)).toBe("inventory_overdue");
  });
});

describe("inventoryLineStatusKey", () => {
  it("associe chaque statut de ligne d'inventaire à la bonne clé de badge", () => {
    expect(inventoryLineStatusKey("no_gap")).toBe("inventory_line_no_gap");
    expect(inventoryLineStatusKey("justified")).toBe("inventory_line_justified");
    expect(inventoryLineStatusKey("to_justify")).toBe("to_justify");
  });
});

describe("libellés de l'intendance", () => {
  it("10 catégories dans l'ordre du registre de l'API", () => {
    expect(ARTICLE_CATEGORY_OPTIONS.map((o) => o.value)).toEqual([
      "jersey",
      "shorts",
      "socks",
      "cleats",
      "balls",
      "bibs",
      "referee",
      "accessories",
      "furniture",
      "misc",
    ]);
  });

  it("« Reprise du registre » parmi les entrées et 11 types au total pour le filtre (ceux de l'API)", () => {
    expect(IN_MOVEMENT_TYPE_OPTIONS.map((o) => o.value)).toContain("in_opening");
    expect(ALL_MOVEMENT_TYPE_OPTIONS).toHaveLength(11);
  });

  it("statut de déclassement -> badge", () => {
    expect(decommissionStatusKey("pending")).toBe("decommission_pending");
    expect(decommissionStatusKey("done")).toBe("decommission_done");
    expect(decommissionStatusKey("cancelled")).toBe("decommission_cancelled");
  });

  it("normalise casse et accents", () => {
    expect(normalizeText("  Éric MBALA ")).toBe("eric mbala");
  });
});

describe("articlesLabel", () => {
  it("agrees « article » with the count (no « 1 articles »)", () => {
    expect(articlesLabel(0)).toBe("0 article");
    expect(articlesLabel(1)).toBe("1 article");
    expect(articlesLabel(2)).toBe("2 articles");
  });
});
