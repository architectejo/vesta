import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ExpenseCategory } from "../../api/treasury";
import { ExpenseCategoryDetailModal } from "./ExpenseCategoryDetailModal";

function makeCategory(overrides: Partial<ExpenseCategory> = {}): ExpenseCategory {
  return {
    id: 1,
    name: "Arbitrage",
    ceiling: "50.00",
    receipt_required: true,
    good_standing_only: true,
    status: "active",
    archived_at: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

describe("ExpenseCategoryDetailModal", () => {
  it("affiche les champs en lecture et propose Modifier / Archiver à un gestionnaire", async () => {
    const onEdit = vi.fn();
    const onArchive = vi.fn();
    const user = userEvent.setup();
    render(
      <ExpenseCategoryDetailModal
        category={makeCategory()}
        currency="USD"
        canEdit
        onClose={vi.fn()}
        onEdit={onEdit}
        onArchive={onArchive}
      />,
    );

    expect(screen.getByText("50 USD")).toBeInTheDocument();
    expect(screen.getByText("Obligatoire")).toBeInTheDocument();
    expect(screen.getByText("Réservée aux membres en ordre")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Modifier" }));
    expect(onEdit).toHaveBeenCalledWith(makeCategory());

    await user.click(screen.getByRole("button", { name: "Plus d'actions" }));
    await user.click(screen.getByRole("button", { name: "Archiver" }));
    expect(onArchive).toHaveBeenCalledWith(makeCategory());
  });

  it("masque Modifier et le menu Archiver pour un rôle en lecture seule", () => {
    render(
      <ExpenseCategoryDetailModal
        category={makeCategory()}
        currency="USD"
        canEdit={false}
        onClose={vi.fn()}
        onEdit={vi.fn()}
        onArchive={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Modifier" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Plus d'actions" })).not.toBeInTheDocument();
  });

  it("n'affiche pas le menu Archiver pour une catégorie déjà archivée", () => {
    render(
      <ExpenseCategoryDetailModal
        category={makeCategory({ status: "archived", archived_at: "2026-09-15T00:00:00Z" })}
        currency="USD"
        canEdit
        onClose={vi.fn()}
        onEdit={vi.fn()}
        onArchive={vi.fn()}
      />,
    );

    expect(screen.getByText("Catégorie archivée.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Plus d'actions" })).not.toBeInTheDocument();
  });
});
