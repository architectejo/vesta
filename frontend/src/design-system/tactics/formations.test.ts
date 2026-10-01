import { describe, expect, it } from "vitest";
import { formationsForSquadSize, slotsForFormation } from "./formations";

describe("formationsForSquadSize", () => {
  it("propose les 8 formations nommées pour un effectif de 11", () => {
    const formations = formationsForSquadSize(11);
    expect(formations).toContain("4-4-2");
    expect(formations).toContain("4-5-1");
    expect(formations).not.toContain("custom");
    expect(formations).toHaveLength(8);
  });

  it("ne propose que « Personnalisée » à effectif réduit (contrainte backend)", () => {
    expect(formationsForSquadSize(7)).toEqual(["custom"]);
    expect(formationsForSquadSize(8)).toEqual(["custom"]);
  });
});

describe("slotsForFormation", () => {
  it("place un gardien et onze emplacements au total pour un 4-4-2", () => {
    const slots = slotsForFormation("4-4-2", 11);
    expect(slots).toHaveLength(11);
    expect(slots.filter((s) => s.positionKind === "goalkeeper")).toHaveLength(1);
    expect(slots.filter((s) => s.positionKind === "defender")).toHaveLength(4);
    expect(slots.filter((s) => s.positionKind === "midfielder")).toHaveLength(4);
    expect(slots.filter((s) => s.positionKind === "forward")).toHaveLength(2);
  });

  it("toutes les coordonnées restent dans 0-100", () => {
    for (const formation of ["4-4-2", "3-5-2", "4-1-4-1"] as const) {
      for (const slot of slotsForFormation(formation, 11)) {
        expect(slot.x).toBeGreaterThanOrEqual(0);
        expect(slot.x).toBeLessThanOrEqual(100);
        expect(slot.y).toBeGreaterThanOrEqual(0);
        expect(slot.y).toBeLessThanOrEqual(100);
      }
    }
  });

  it("fournit une disposition par défaut à effectif réduit", () => {
    const slots7 = slotsForFormation("custom", 7);
    expect(slots7.length).toBeGreaterThan(0);
    expect(slots7.some((s) => s.positionKind === "goalkeeper")).toBe(true);
  });

  it("resserre la ligne d'attaquants vers l'axe plutôt que de l'étaler jusqu'aux touches", () => {
    const slots = slotsForFormation("4-4-2", 11);
    const forwards = slots.filter((s) => s.positionKind === "forward").map((s) => s.x);
    const defenders = slots.filter((s) => s.positionKind === "defender").map((s) => s.x);
    // Les attaquants restent nettement plus centraux que les défenseurs,
    // qui eux couvrent la largeur du terrain.
    expect(Math.min(...forwards)).toBeGreaterThan(Math.min(...defenders));
    expect(Math.max(...forwards)).toBeLessThan(Math.max(...defenders));
    for (const x of forwards) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(100);
    }
  });

  it("décale la double sentinelle du 4-2-3-1 des milieux offensifs plutôt que de les empiler à la verticale (« comme des pistons »)", () => {
    const slots = slotsForFormation("4-2-3-1", 11);
    const linesByY = new Map<number, number[]>();
    for (const slot of slots.filter((s) => s.positionKind === "midfielder")) {
      const xs = linesByY.get(slot.y) ?? [];
      xs.push(slot.x);
      linesByY.set(slot.y, xs);
    }
    const lines = [...linesByY.entries()].sort(([a], [b]) => a - b);
    expect(lines).toHaveLength(2);
    const [pivot, advanced] = lines.map(([, xs]) => xs);
    expect(pivot).toHaveLength(2);
    expect(advanced).toHaveLength(3);
    // Aucune abscisse de la double sentinelle ne doit coïncider avec une
    // abscisse de la ligne de milieux offensifs : sinon les deux pions se
    // superposent verticalement sur le terrain.
    for (const x of pivot!) {
      expect(advanced).not.toContain(x);
    }
  });
});
