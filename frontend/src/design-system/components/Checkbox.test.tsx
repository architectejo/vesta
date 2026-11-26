import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Checkbox } from "./Checkbox";

function row(): HTMLElement {
  return screen.getByText("J'accepte").closest("label") as HTMLElement;
}

describe("Checkbox", () => {
  it("coche la case quand on touche le libellé, pas seulement la case", () => {
    const onChange = vi.fn();
    render(<Checkbox checked={false} onChange={onChange} label="J'accepte" />);
    fireEvent.click(screen.getByText("J'accepte"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("donne à la ligne une zone tactile d'au moins 36 px sans grossir la case ni le texte", () => {
    // Vérification visuelle B7 (360 px) : la zone cliquable ne faisait que 20 px.
    // jsdom ne calcule pas la mise en page : on fige les classes qui la portent.
    render(<Checkbox checked={false} onChange={() => {}} label="J'accepte" />);
    const classes = row().className.split(/\s+/);
    expect(classes).toContain("min-h-control-sm"); // 36 px
    expect(classes).toContain("py-2");
    // Marge de clic invisible : 36 + 2 × 4 = 44 px (§1.3).
    expect(classes).toContain("before:-inset-y-1");
    expect(classes).toContain("relative");
    expect(classes).toContain("text-sm");
    const box = screen.getByRole("checkbox");
    expect(box.className.split(/\s+/)).toEqual(expect.arrayContaining(["h-4", "w-4"]));
  });

  it("n'appelle pas onChange quand la case est désactivée", () => {
    const onChange = vi.fn();
    render(<Checkbox checked={false} onChange={onChange} label="J'accepte" disabled />);
    fireEvent.click(screen.getByText("J'accepte"));
    expect(onChange).not.toHaveBeenCalled();
    expect(row().className).toContain("cursor-not-allowed");
  });

  it("affiche l'erreur sous la ligne", () => {
    render(<Checkbox checked={false} onChange={() => {}} label="J'accepte" error="Obligatoire." />);
    expect(screen.getByText("Obligatoire.")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toHaveAttribute("aria-invalid", "true");
  });
});
