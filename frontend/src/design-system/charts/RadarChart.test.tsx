import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RadarChart } from "./RadarChart";

const AXES = [{ label: "Vitesse" }, { label: "Endurance physique" }, { label: "Technique" }, { label: "Frappe" }, { label: "Défense" }];

describe("RadarChart", () => {
  it("trace un polygone par série avec des tracés différents et une légende", () => {
    const { container } = render(
      <RadarChart
        title="Comparaison"
        axes={AXES}
        series={[
          { name: "Joueur Un", values: [80, 60, 70, 50, 40] },
          { name: "Joueur Deux", values: [50, 70, 60, 80, 90] },
        ]}
      />,
    );
    const polygons = Array.from(container.querySelectorAll("polygon[data-series]"));
    expect(polygons).toHaveLength(2);
    expect(polygons[0]!.getAttribute("stroke-dasharray")).toBeNull();
    expect(polygons[1]!.getAttribute("stroke-dasharray")).toBe("6 4");
    expect(screen.getAllByText("Joueur Un").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Joueur Deux").length).toBeGreaterThan(0);
  });

  it("écrit les libellés d'axe complets (multi-lignes, sans troncature) et les valeurs d'une série unique", () => {
    render(<RadarChart title="Profil" axes={AXES} series={[{ name: "Joueur Un", values: [80, 60, 70, 50, 40] }]} />);
    expect(screen.getByText("Endurance")).toBeInTheDocument();
    expect(screen.getByText("physique")).toBeInTheDocument();
    expect(screen.getAllByText("80").length).toBeGreaterThan(0);
    expect(screen.getByRole("img", { name: /Vitesse 80/ })).toBeInTheDocument();
  });

  it("explique qu'il faut 3 critères au minimum", () => {
    render(<RadarChart title="Profil" axes={[{ label: "A" }, { label: "B" }]} series={[{ name: "S", values: [1, 2] }]} />);
    expect(screen.getByText("Il faut au moins trois critères pour tracer un radar.")).toBeInTheDocument();
  });

  it("état vide sans série ou sans valeur", () => {
    render(<RadarChart title="Profil" axes={AXES} series={[{ name: "S", values: [null, null, null, null, null] }]} emptyMessage="Aucune évaluation." />);
    expect(screen.getByText("Aucune évaluation.")).toBeInTheDocument();
  });

  it("borne les valeurs hors échelle sans erreur", () => {
    render(<RadarChart title="Profil" axes={AXES} maxValue={10} series={[{ name: "S", values: [0, 10, 99, -5, 5] }]} />);
    expect(screen.getByRole("img", { name: /Profil/ })).toBeInTheDocument();
  });

  it("onSelect sur un axe : clic et Espace", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<RadarChart title="Profil" axes={AXES} series={[{ name: "S", values: [1, 2, 3, 4, 5] }]} onSelect={onSelect} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(5);
    await user.click(buttons[3]!);
    expect(onSelect).toHaveBeenLastCalledWith(3);
    buttons[1]!.focus();
    await user.keyboard(" ");
    expect(onSelect).toHaveBeenLastCalledWith(1);
  });

  it("donne le tableau des valeurs", () => {
    render(<RadarChart title="Profil" axes={AXES} series={[{ name: "Joueur Un", values: [1, 2, 3, 4, 5] }]} />);
    expect(screen.getByRole("table", { hidden: true })).toBeInTheDocument();
  });
});
