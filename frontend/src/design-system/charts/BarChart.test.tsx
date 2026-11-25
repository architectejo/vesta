import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BarChart } from "./BarChart";

const MONTHS = ["juin", "juil.", "août", "sept.", "oct.", "nov."];

describe("BarChart", () => {
  it("écrit la valeur de chaque barre et nomme la figure", () => {
    render(<BarChart title="Encaissé par mois" categories={MONTHS} series={[{ name: "Encaissé", values: [100, 200, 150, 0, 300, 250] }]} unit="$" />);
    expect(screen.getByRole("figure", { name: "Encaissé par mois" })).toBeInTheDocument();
    expect(screen.getAllByText("300 $").length).toBeGreaterThan(0);
    expect(screen.getAllByText("0 $").length).toBeGreaterThan(0);
    expect(screen.getByRole("img", { name: /nov\. : 250 \$/ })).toBeInTheDocument();
  });

  it("n'affiche aucune barre pour une valeur absente et un tiret dans le tableau", () => {
    const { container } = render(<BarChart title="T" categories={["a", "b"]} series={[{ name: "S", values: [5, null] }]} />);
    expect(container.querySelectorAll("rect[fill='var(--color-series-1)']")).toHaveLength(1);
    const table = screen.getByRole("table", { hidden: true });
    expect(within(table).getAllByText("—")).toHaveLength(1);
  });

  it("affiche l'état vide sans donnée", () => {
    render(<BarChart title="T" categories={[]} series={[]} emptyMessage="Aucune dépense sur la période." />);
    expect(screen.getByText("Aucune dépense sur la période.")).toBeInTheDocument();
  });

  it("groupé : légende textuelle et motif différent pour la 2e série", () => {
    const { container } = render(
      <BarChart
        title="Caisse"
        categories={["oct.", "nov."]}
        series={[
          { name: "Encaissé", values: [100, 200] },
          { name: "Dépensé", values: [50, 80] },
        ]}
      />,
    );
    expect(screen.getAllByText("Encaissé").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Dépensé").length).toBeGreaterThan(0);
    expect(container.querySelectorAll("rect[fill^='url(#']").length).toBeGreaterThan(0);
  });

  it("empilé : écrit le total et la colonne Total du tableau", () => {
    render(
      <BarChart
        title="Cartons"
        stacked
        categories={["oct.", "nov."]}
        series={[
          { name: "Jaunes", values: [4, 7] },
          { name: "Rouges", values: [1, 0] },
        ]}
      />,
    );
    expect(screen.getByRole("img", { name: /oct\. : total 5/ })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Total", hidden: true })).toBeInTheDocument();
  });

  it("horizontal : étiquette complète au-dessus de chaque barre, jamais tronquée", () => {
    render(
      <BarChart
        title="Dépenses par catégorie"
        orientation="horizontal"
        categories={["Équipement sportif et entretien du terrain", "Transport"]}
        series={[{ name: "Montant", values: [900, 120] }]}
      />,
    );
    expect(screen.getAllByText("Équipement sportif et entretien du terrain").length).toBeGreaterThan(0);
    expect(screen.getAllByText("900").length).toBeGreaterThan(0);
  });

  it("défile dans son cadre quand il y a beaucoup de catégories (pas de débordement de page)", () => {
    const months = Array.from({ length: 12 }, (_, i) => `m${i + 1}`);
    render(<BarChart title="Année" categories={months} series={[{ name: "S", values: months.map((_, i) => i * 10) }]} />);
    const region = screen.getByRole("region", { name: "Année (défilement horizontal)" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(region.className).toContain("overflow-x-auto");
  });

  it("se cale à droite à l'ouverture et laisse le défilement manuel", () => {
    const sw = vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(900);
    const cw = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(300);
    const months = Array.from({ length: 12 }, (_, i) => `m${i + 1}`);
    render(<BarChart title="Année" categories={months} series={[{ name: "S", values: months.map((_, i) => i) }]} />);
    const region = screen.getByRole("region", { name: "Année (défilement horizontal)" });
    expect(region.scrollLeft).toBe(600);
    region.scrollLeft = 0;
    expect(region.scrollLeft).toBe(0);
    sw.mockRestore();
    cw.mockRestore();
  });

  it("onSelect : clic, Entrée et Espace", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<BarChart title="T" categories={["a", "b", "c"]} series={[{ name: "S", values: [1, 2, 3] }]} onSelect={onSelect} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(3);
    await user.click(buttons[2]!);
    expect(onSelect).toHaveBeenLastCalledWith(2);
    buttons[0]!.focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    expect(onSelect).toHaveBeenCalledTimes(3);
    expect(onSelect).toHaveBeenLastCalledWith(0);
  });

  it("gère les grandes valeurs et les valeurs négatives", () => {
    render(<BarChart title="Solde" categories={["a", "b"]} series={[{ name: "S", values: [-50_000, 2_000_000] }]} />);
    expect(screen.getByRole("img", { name: /Solde/ })).toBeInTheDocument();
  });

  it("affiche le chargement", async () => {
    render(<BarChart title="T" categories={["a"]} series={[{ name: "S", values: [1] }]} state="loading" />);
    expect(await screen.findByText("Chargement…")).toBeInTheDocument();
  });
});
