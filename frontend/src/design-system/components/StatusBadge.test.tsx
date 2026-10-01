import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("affiche le libellé français dérivé de la clé", () => {
    render(<StatusBadge status="in_debt" />);
    expect(screen.getByText("En dette")).toBeInTheDocument();
  });

  it("ajoute le complément après le libellé", () => {
    render(<StatusBadge status="in_debt" detail="20 $" />);
    expect(screen.getByText("En dette · 20 $")).toBeInTheDocument();
  });

  it("ne repose jamais sur la seule couleur : le libellé est toujours présent", () => {
    render(<StatusBadge status="suspended" />);
    expect(screen.getByText("Suspendu")).toBeInTheDocument();
  });
});
