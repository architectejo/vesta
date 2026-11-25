import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FormStrip, type FormStripResult } from "./FormStrip";

const RESULTS: FormStripResult[] = [
  { outcome: "win", opponent: "Équipe fictive A", score: "3-1" },
  { outcome: "draw", opponent: "Équipe fictive B", score: "1-1" },
  { outcome: "loss", opponent: "Équipe fictive C", score: "0-2" },
];

describe("FormStrip", () => {
  it("écrit V, N, D dans les pastilles et décrit chaque match", () => {
    render(<FormStrip results={RESULTS} />);
    expect(screen.getByText("V")).toBeInTheDocument();
    expect(screen.getByText("N")).toBeInTheDocument();
    expect(screen.getByText("D")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Victoire contre Équipe fictive A, 3-1" })).toBeInTheDocument();
  });

  it("limite à 5 pastilles", () => {
    const many = Array.from({ length: 8 }, () => ({ outcome: "win" as const }));
    render(<FormStrip results={many} />);
    expect(screen.getAllByText("V")).toHaveLength(5);
  });

  it("affiche l'état vide", () => {
    render(<FormStrip results={[]} emptyMessage="Aucun match joué sur la période." />);
    expect(screen.getByText("Aucun match joué sur la période.")).toBeInTheDocument();
  });

  it("onSelect : clic et clavier, cible de 36 px", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<FormStrip results={RESULTS} onSelect={onSelect} />);
    const button = screen.getByRole("button", { name: /Défaite contre Équipe fictive C/ });
    expect(button.className).toContain("h-9");
    await user.click(button);
    expect(onSelect).toHaveBeenCalledWith(2, RESULTS[2]);
    button.focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it("affiche l'erreur avec Réessayer", async () => {
    const onRetry = vi.fn();
    render(<FormStrip results={[]} state="error" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(onRetry).toHaveBeenCalled();
  });
});
