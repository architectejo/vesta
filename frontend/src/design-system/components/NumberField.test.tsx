import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NumberField } from "./NumberField";

describe("NumberField", () => {
  it("incrémente et décrémente avec les boutons − / +", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<NumberField label="Numéro" value={5} onChange={onChange} min={1} max={99} />);
    await user.click(screen.getByRole("button", { name: "Augmenter Numéro" }));
    expect(onChange).toHaveBeenCalledWith(6);
    await user.click(screen.getByRole("button", { name: "Diminuer Numéro" }));
    expect(onChange).toHaveBeenCalledWith(4);
  });

  it("respecte les bornes min et max", () => {
    const onChange = vi.fn();
    render(<NumberField label="Numéro" value={1} onChange={onChange} min={1} max={2} />);
    expect(screen.getByRole("button", { name: "Diminuer Numéro" })).toBeDisabled();
  });
});
