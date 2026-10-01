import { describe, expect, it } from "vitest";
import { cellAmountText, cellVisual, GRID_STATE_TO_STATUS_KEY } from "./gridCellVisuals";

describe("cellAmountText", () => {
  it("affiche le montant affecté pour une cellule payée", () => {
    expect(cellAmountText({ state: "paid", allocated: "20.00" })).toBe("20");
  });

  it("affiche le montant affecté pour une cellule partielle", () => {
    expect(cellAmountText({ state: "partial", allocated: "5.00" })).toBe("5");
  });

  it("affiche 0 pour une cellule impayée échue, quel que soit le montant dû", () => {
    expect(cellAmountText({ state: "overdue", allocated: "0.00" })).toBe("0");
  });

  it("affiche un tiret pour une cellule à venir", () => {
    expect(cellAmountText({ state: "upcoming", allocated: "0.00" })).toBe("—");
  });

  it("cotisation libre : un tiret sans versement, le montant sinon", () => {
    expect(cellAmountText({ state: "free", allocated: "0.00" })).toBe("—");
    expect(cellAmountText({ state: "free", allocated: "15.00" })).toBe("15");
  });
});

describe("cellVisual", () => {
  it("n'affiche jamais de fond rouge pour une cotisation libre (4.4.7 : jamais de dette)", () => {
    const visual = cellVisual({ state: "free", allocated: "0.00" });
    expect(visual.bgClass).not.toContain("unpaid");
    expect(visual.dot).toBeNull();
  });

  it("associe l'état impayé échu au fond rouge et une pastille", () => {
    const visual = cellVisual({ state: "overdue", allocated: "0.00" });
    expect(visual.bgClass).toBe("bg-cell-unpaid-bg");
    expect(visual.dot).not.toBeNull();
  });

  it("associe chaque état de cellule à une clé de statut connue", () => {
    expect(GRID_STATE_TO_STATUS_KEY.paid).toBe("grid_paid");
    expect(GRID_STATE_TO_STATUS_KEY.partial).toBe("grid_partial");
    expect(GRID_STATE_TO_STATUS_KEY.overdue).toBe("grid_overdue");
    expect(GRID_STATE_TO_STATUS_KEY.upcoming).toBe("grid_upcoming");
    expect(GRID_STATE_TO_STATUS_KEY.free).toBe("grid_free");
    expect(GRID_STATE_TO_STATUS_KEY.not_due).toBe("grid_not_due");
  });
});
