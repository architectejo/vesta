import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FilterChips } from "./FilterChips";

const OPTIONS = [
  { value: "ball", label: "Ballons" },
  { value: "kit", label: "Maillots" },
] as const;

describe("FilterChips", () => {
  it("affiche « Toutes » en premier puis les options, l'actif en aria-pressed", () => {
    const onChange = vi.fn();
    render(<FilterChips label="Catégorie" value="kit" onChange={onChange} options={[...OPTIONS]} />);
    const chips = screen.getAllByRole("button");
    expect(chips.map((c) => c.textContent)).toEqual(["Toutes", "Ballons", "Maillots"]);
    expect(screen.getByRole("button", { name: "Maillots" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Toutes" }));
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("donne 36 px de haut à chaque puce (vérification visuelle B7)", () => {
    render(<FilterChips label="Catégorie" value="" onChange={() => {}} options={[...OPTIONS]} />);
    for (const chip of screen.getAllByRole("button")) {
      const classes = chip.className.split(/\s+/);
      expect(classes).toContain("h-control-sm");
      expect(classes.some((c) => /^h-(7|8)$/.test(c))).toBe(false);
    }
  });
});
