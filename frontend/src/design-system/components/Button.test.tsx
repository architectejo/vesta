import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";

describe("Button", () => {
  it("affiche son libellé et déclenche onClick", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<Button onClick={onClick}>Enregistrer</Button>);

    const button = screen.getByRole("button", { name: "Enregistrer" });
    await user.click(button);

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("affiche le libellé de chargement et se désactive quand loading est vrai", () => {
    render(
      <Button loading loadingLabel="Enregistrement…">
        Enregistrer
      </Button>,
    );

    const button = screen.getByRole("button", { name: "Enregistrement…" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("n'appelle pas onClick quand disabled", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <Button disabled onClick={onClick}>
        Enregistrer
      </Button>,
    );

    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(onClick).not.toHaveBeenCalled();
  });
});
