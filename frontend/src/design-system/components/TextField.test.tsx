import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PasswordField, TextField } from "./TextField";

describe("TextField", () => {
  it("affiche le libellé, l'aide et appelle onChange", async () => {
    const onChange = vi.fn();
    render(<TextField label="Email" value="" onChange={onChange} help="Votre identifiant" />);
    expect(screen.getByText("Votre identifiant")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Email"), "a");
    expect(onChange).toHaveBeenCalledWith("a");
  });

  it("affiche l'erreur au lieu de l'aide et marque aria-invalid", () => {
    render(
      <TextField
        label="Email"
        value=""
        onChange={() => {}}
        help="ignorée"
        error="Ce champ est obligatoire."
      />,
    );
    expect(screen.getByText("Ce champ est obligatoire.")).toBeInTheDocument();
    expect(screen.queryByText("ignorée")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });

  it("affiche « (facultatif) » quand demandé", () => {
    render(<TextField label="Téléphone" value="" onChange={() => {}} optional />);
    expect(screen.getByText("(facultatif)")).toBeInTheDocument();
  });
});

describe("PasswordField", () => {
  it("bascule entre masqué et affiché", async () => {
    render(<PasswordField label="Mot de passe" value="secret" onChange={() => {}} />);
    const input = screen.getByLabelText("Mot de passe") as HTMLInputElement;
    expect(input.type).toBe("password");
    await userEvent.click(screen.getByText("Afficher"));
    expect(input.type).toBe("text");
    await userEvent.click(screen.getByText("Masquer"));
    expect(input.type).toBe("password");
  });
});
