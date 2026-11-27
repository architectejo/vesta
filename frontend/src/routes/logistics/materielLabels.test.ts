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
  formatQuantity,
  piecesLabel,
  quantityLabelOf,
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

describe("formatQuantity (accord en nombre, même règle que l'API)", () => {
  it("singulier pour 0 et 1, pluriel à partir de 2", () => {
    expect(formatQuantity(0, "pièce")).toBe("0 pièce");
    expect(formatQuantity(1, "pièce")).toBe("1 pièce");
    expect(formatQuantity(26, "pièce")).toBe("26 pièces");
    expect(formatQuantity(-3, "pièce")).toBe("-3 pièces");
  });

  it("pluriels en x, unités invariables et formes déjà au pluriel", () => {
    expect(formatQuantity(2, "jeu")).toBe("2 jeux");
    expect(formatQuantity(4, "seau")).toBe("4 seaux");
    expect(formatQuantity(3, "kg")).toBe("3 kg");
    expect(formatQuantity(5, "pièces")).toBe("5 pièces");
    expect(formatQuantity(2, "boîte de 6")).toBe("2 boîte de 6");
    expect(formatQuantity(2, "")).toBe("2");
  });

  it("piecesLabel : « 1 pièce », « 3 pièces »", () => {
    expect(piecesLabel(1)).toBe("1 pièce");
    expect(piecesLabel(3)).toBe("3 pièces");
  });

  it("quantityLabelOf : libellé de l'API d'abord, repli accordé sinon", () => {
    expect(quantityLabelOf({ quantity: 26, unit: "pièce", quantity_label: "26 pièces" })).toBe("26 pièces");
    expect(quantityLabelOf({ quantity: 26, unit: "pièce" })).toBe("26 pièces");
    expect(quantityLabelOf({ quantity: 1, unit: "pièce", quantity_label: "" })).toBe("1 pièce");
  });
});
