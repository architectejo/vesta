import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("affiche le message par défaut de la variante erreur", () => {
    render(<EmptyState variant="error" />);
    expect(screen.getByText("Impossible de charger cette section.")).toBeInTheDocument();
  });

  it("n'affiche pas d'action si onAction n'est pas fourni (rôle insuffisant)", () => {
    render(<EmptyState message="Aucun joueur." actionLabel="Ajouter un joueur" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("affiche et déclenche l'action quand elle est fournie", async () => {
    const onAction = vi.fn();
    const user = userEvent.setup();
    render(
      <EmptyState
        variant="error"
        actionLabel="Réessayer"
        onAction={onAction}
        message="Impossible de charger cette section."
      />,
    );

    await user.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(onAction).toHaveBeenCalledTimes(1);
  });
});
