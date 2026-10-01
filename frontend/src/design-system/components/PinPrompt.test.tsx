import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PinPrompt } from "./PinPrompt";

describe("PinPrompt", () => {
  it("valide automatiquement au 6e chiffre", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <PinPrompt
        open
        description="Valider le paiement de 10 USD pour Jean K."
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText("Votre code PIN"), "123456");
    expect(onSubmit).toHaveBeenCalledWith("123456");
  });

  it("désactive « Confirmer » tant que moins de 4 chiffres sont saisis", async () => {
    const user = userEvent.setup();
    render(
      <PinPrompt open description="Valider" onSubmit={vi.fn()} onClose={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Confirmer" })).toBeDisabled();
    await user.type(screen.getByLabelText("Votre code PIN"), "123");
    expect(screen.getByRole("button", { name: "Confirmer" })).toBeDisabled();
    await user.type(screen.getByLabelText("Votre code PIN"), "4");
    expect(screen.getByRole("button", { name: "Confirmer" })).toBeEnabled();
  });

  it("affiche l'erreur et efface la saisie pour permettre une nouvelle tentative", () => {
    const { rerender } = render(
      <PinPrompt open description="Valider" onSubmit={vi.fn()} onClose={vi.fn()} />,
    );
    rerender(
      <PinPrompt
        open
        description="Valider"
        onSubmit={vi.fn()}
        onClose={vi.fn()}
        error="Code PIN incorrect. Il vous reste 2 essai(s)."
      />,
    );
    expect(
      screen.getByText("Code PIN incorrect. Il vous reste 2 essai(s)."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Votre code PIN")).toHaveValue("");
  });
});
