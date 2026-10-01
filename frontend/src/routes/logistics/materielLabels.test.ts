import { describe, expect, it } from "vitest";
import {
  equipmentLineStatusKey,
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
