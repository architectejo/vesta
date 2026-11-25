import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StackedBar } from "./StackedBar";

const SEGMENTS = [
  { label: "En ordre", value: 24, family: "success" as const },
  { label: "En dette", value: 6, family: "danger" as const },
  { label: "En attente", value: 0, family: "warning" as const },
  { label: "Suspendus", value: 1, family: "suspended" as const },
];

describe("StackedBar", () => {
  it("écrit libellé, nombre et pourcentage de chaque segment", () => {
    render(<StackedBar title="Situation de l'effectif" segments={SEGMENTS} />);
    expect(screen.getByRole("figure", { name: "Situation de l'effectif" })).toBeInTheDocument();
    expect(screen.getAllByText("En ordre").length).toBeGreaterThan(0);
    expect(screen.getAllByText("24").length).toBeGreaterThan(0);
    expect(screen.getAllByText("77,4 %").length).toBeGreaterThan(0);
    // Segment à zéro : écrit dans la légende, absent de la barre.
    expect(screen.getAllByText("En attente").length).toBeGreaterThan(0);
  });

  it("utilise les couleurs de statut et des motifs différents par position", () => {
    render(<StackedBar title="Effectif" segments={SEGMENTS} />);
    const bar = screen.getByRole("img", { name: /Total 31/ });
    const segments = Array.from(bar.children) as HTMLElement[];
    expect(segments).toHaveLength(3);
    expect(segments[0]!.style.backgroundColor).toContain("--color-status-success-dot");
    expect(segments[1]!.style.backgroundImage).not.toBe("");
  });

  it("affiche l'état vide quand le total est nul", () => {
    render(<StackedBar title="Effectif" segments={[{ label: "A", value: 0 }]} emptyMessage="Aucune donnée." />);
    expect(screen.getByText("Aucune donnée.")).toBeInTheDocument();
  });

  it("ne casse pas sur une valeur négative ou invalide", () => {
    render(<StackedBar title="Effectif" segments={[{ label: "A", value: -4 }, { label: "B", value: Number.NaN }, { label: "C", value: 2 }]} />);
    expect(screen.getByRole("img", { name: /Total 2/ })).toBeInTheDocument();
  });

  it("onSelect : segments et lignes de légende cliquables au clavier", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<StackedBar title="Effectif" segments={SEGMENTS} onSelect={onSelect} />);
    await user.click(screen.getAllByRole("button", { name: /En dette : 6/ })[0]!);
    expect(onSelect).toHaveBeenLastCalledWith(1, expect.objectContaining({ label: "En dette" }));
    const legendButtons = screen.getAllByRole("button").filter((b) => b.textContent?.includes("Suspendus"));
    legendButtons[0]!.focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenLastCalledWith(3, expect.objectContaining({ label: "Suspendus" }));
  });

  it("fournit le tableau de données", () => {
    render(<StackedBar title="Effectif" segments={SEGMENTS} />);
    expect(screen.getByText("Voir les données")).toBeInTheDocument();
    expect(screen.getByRole("table", { hidden: true })).toBeInTheDocument();
  });
});
