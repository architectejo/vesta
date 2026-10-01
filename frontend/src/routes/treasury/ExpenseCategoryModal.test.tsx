import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ExpenseCategory } from "../../api/treasury";
import { ExpenseCategoryModal } from "./ExpenseCategoryModal";

function makeCategory(overrides: Partial<ExpenseCategory> = {}): ExpenseCategory {
  return {
    id: 1,
    name: "Arbitrage",
    ceiling: "50.00",
    receipt_required: true,
    good_standing_only: false,
    status: "active",
    archived_at: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

describe("ExpenseCategoryModal", () => {
  it("exige un nom avant d'enregistrer une nouvelle catégorie", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <ExpenseCategoryModal
        open
        currency="USD"
        isSubmitting={false}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(await screen.findByText("Ce champ est obligatoire.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("pré-remplit les champs d'une catégorie existante et enregistre les modifications", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <ExpenseCategoryModal
        open
        category={makeCategory()}
        currency="USD"
        isSubmitting={false}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByLabelText("Nom")).toHaveValue("Arbitrage");
    expect(screen.getByLabelText("Justificatif obligatoire")).toBeChecked();
    await user.click(screen.getByLabelText("Réservée aux membres en ordre"));
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(onSubmit).toHaveBeenCalledWith({
      name: "Arbitrage",
      ceiling: "50.00",
      receipt_required: true,
      good_standing_only: true,
    });
  });

  it("affiche le message d'erreur renvoyé par l'API", () => {
    render(
      <ExpenseCategoryModal
        open
        currency="USD"
        isSubmitting={false}
        submitError="Une catégorie porte déjà ce nom."
        onClose={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText("Une catégorie porte déjà ce nom.")).toBeInTheDocument();
  });
});
