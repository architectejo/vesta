import { describe, expect, it } from "vitest";
import type { ExpenseCategory } from "../../api/treasury";
import { describeExpenseCategory, expenseStatusKey } from "./expenseLabels";

function makeCategory(overrides: Partial<ExpenseCategory> = {}): ExpenseCategory {
  return {
    id: 1,
    name: "Arbitrage",
    ceiling: null,
    receipt_required: true,
    good_standing_only: false,
    status: "active",
    archived_at: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

describe("expenseStatusKey", () => {
  it("préfixe chaque statut de dépense pour la clé de couleur du design system", () => {
    expect(expenseStatusKey("pending")).toBe("expense_pending");
    expect(expenseStatusKey("refused")).toBe("expense_refused");
    expect(expenseStatusKey("released")).toBe("expense_released");
    expect(expenseStatusKey("justified")).toBe("expense_justified");
    expect(expenseStatusKey("unjustified")).toBe("expense_unjustified");
  });
});

describe("describeExpenseCategory", () => {
  it("affiche le justificatif facultatif sans plafond ni réservation", () => {
    const category = makeCategory({ receipt_required: false });
    expect(describeExpenseCategory(category, "USD")).toBe("Justificatif facultatif");
  });

  it("affiche le plafond, le justificatif obligatoire et la réservation", () => {
    const category = makeCategory({ ceiling: "50.00", good_standing_only: true });
    expect(describeExpenseCategory(category, "USD")).toBe(
      "Plafond : 50 USD · Justificatif obligatoire · Réservée aux membres en ordre",
    );
  });
});
