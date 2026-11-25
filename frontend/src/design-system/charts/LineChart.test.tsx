import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LineChart } from "./LineChart";

const LABELS = ["3 nov.", "10 nov.", "17 nov.", "24 nov."];

describe("LineChart", () => {
  it("rend une figure nommée, un résumé lisible et la dernière valeur écrite", () => {
    render(
      <LineChart
        title="Taux de présence"
        labels={LABELS}
        series={[{ name: "Présence", values: [60, 80, 70, 72] }]}
        unit="%"
        reference={{ value: 74, label: "Moyenne" }}
      />,
    );
    expect(screen.getByRole("figure", { name: "Taux de présence" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /dernière valeur 72 %/ })).toBeInTheDocument();
    expect(screen.getAllByText("72 %").length).toBeGreaterThan(0);
    expect(screen.getByText("Moyenne 74 %")).toBeInTheDocument();
  });

  it("propose les données sous forme de tableau repliable", () => {
    render(<LineChart title="Taux" labels={LABELS} series={[{ name: "Présence", values: [60, null, 70, 72] }]} />);
    expect(screen.getByText("Voir les données")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Taux", hidden: true });
    expect(table).toBeInTheDocument();
    expect(screen.getAllByRole("row", { hidden: true })).toHaveLength(5);
  });

  it("affiche l'état vide quand toutes les valeurs sont absentes", () => {
    render(
      <LineChart
        title="Taux"
        labels={LABELS}
        series={[{ name: "Présence", values: [null, null, null, null] }]}
        emptyMessage="Aucune séance sur la période."
      />,
    );
    expect(screen.getByText("Aucune séance sur la période.")).toBeInTheDocument();
  });

  it("accepte un seul point et des valeurs nulles (0)", () => {
    const { container } = render(<LineChart title="Taux" labels={["3 nov."]} series={[{ name: "Présence", values: [0] }]} />);
    expect(container.querySelectorAll("[data-point]")).toHaveLength(1);
    expect(container.querySelector("path")).toBeNull();
  });

  it("interrompt la courbe aux valeurs absentes", () => {
    const { container } = render(
      <LineChart title="Taux" labels={["a", "b", "c", "d", "e"]} series={[{ name: "S", values: [1, 2, null, 4, 5] }]} />,
    );
    expect(container.querySelectorAll("path")).toHaveLength(2);
  });

  it("tient les grandes valeurs sans casser (échelle compacte)", () => {
    render(<LineChart title="Montants" labels={["a", "b"]} series={[{ name: "S", values: [1_000_000, 2_500_000] }]} />);
    expect(screen.getByRole("img", { name: /Montants/ })).toBeInTheDocument();
  });

  it("distingue la 2e série par un tracé en tirets et une légende", () => {
    const { container } = render(
      <LineChart
        title="Comparaison"
        labels={LABELS}
        series={[
          { name: "Encaissé", values: [1, 2, 3, 4] },
          { name: "Dû", values: [2, 2, 3, 5] },
        ]}
      />,
    );
    const dashes = Array.from(container.querySelectorAll("path")).map((p) => p.getAttribute("stroke-dasharray"));
    expect(dashes).toContain("6 4");
    expect(screen.getAllByText("Encaissé").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Dû").length).toBeGreaterThan(0);
  });

  it("appelle onSelect au clic, à Entrée et à Espace (focus visible par tabIndex)", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<LineChart title="Taux" labels={LABELS} series={[{ name: "Présence", values: [60, 80, 70, 72] }]} onSelect={onSelect} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(4);
    expect(buttons[1]).toHaveAccessibleName("10 nov. : 80");
    await user.click(buttons[1]!);
    expect(onSelect).toHaveBeenLastCalledWith(1);
    buttons[2]!.focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenLastCalledWith(2);
    await user.keyboard(" ");
    expect(onSelect).toHaveBeenCalledTimes(3);
  });

  it("affiche le chargement puis l'erreur avec « Réessayer »", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<LineChart title="Taux" labels={LABELS} series={[]} state="loading" />);
    expect(await screen.findByText("Chargement…")).toBeInTheDocument();
    rerender(<LineChart title="Taux" labels={LABELS} series={[]} state="error" onRetry={onRetry} />);
    await user.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("écrit la ligne de référence dans la légende, pas sur le tracé", () => {
    const { container } = render(
      <LineChart
        title="Taux"
        labels={LABELS}
        series={[{ name: "Présence", values: [60, 80, 70, 34.88] }]}
        unit="%"
        reference={{ value: 34.88, label: "Moyenne" }}
      />,
    );
    expect(screen.getByText("Moyenne 34,9 %").closest("svg")).toBeNull();
    expect(container.querySelector("svg text")?.textContent).not.toMatch(/Moyenne/);
  });

  it("se cale à droite quand la courbe défile (mois récent visible)", () => {
    const sw = vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(900);
    const cw = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(300);
    const labels = Array.from({ length: 12 }, (_, i) => `m${i + 1}`);
    render(<LineChart title="Courbe" labels={labels} series={[{ name: "A", values: labels.map((_, i) => i) }]} onSelect={() => undefined} />);
    const region = screen.getByRole("region", { name: "Courbe (défilement horizontal)" });
    expect(region.scrollLeft).toBe(600);
    sw.mockRestore();
    cw.mockRestore();
  });
});
