import { describe, expect, it } from "vitest";
import { compareByPositionThenName, groupByPosition, matchesPositionFilter, positionGroupKey } from "./positionGroups";

describe("positionGroups", () => {
  it("poste vide ou inconnu : groupe « Sans poste »", () => {
    expect(positionGroupKey("")).toBe("none");
    expect(positionGroupKey("libero")).toBe("none");
    expect(positionGroupKey(null)).toBe("none");
    expect(positionGroupKey("defender")).toBe("defender");
  });

  it("« Tous » laisse tout passer ; une puce exclut le joueur sans poste", () => {
    expect(matchesPositionFilter("", "")).toBe(true);
    expect(matchesPositionFilter("", "goalkeeper")).toBe(false);
    expect(matchesPositionFilter("goalkeeper", "goalkeeper")).toBe(true);
    expect(matchesPositionFilter("forward", "goalkeeper")).toBe(false);
  });

  it("trie gardiens, défenseurs, milieux, attaquants, sans poste, puis par nom (accents ignorés)", () => {
    const items = [
      { position: "", name: "Aaron" },
      { position: "forward", name: "Émile" },
      { position: "forward", name: "David" },
      { position: "midfielder", name: "Zed" },
      { position: "goalkeeper", name: "Yann" },
      { position: "defender", name: "Bob" },
    ];
    expect([...items].sort(compareByPositionThenName).map((i) => i.name)).toEqual([
      "Yann",
      "Bob",
      "Zed",
      "David",
      "Émile",
      "Aaron",
    ]);
  });

  it("groupe dans l'ordre des postes, sans groupe vide", () => {
    const groups = groupByPosition(
      [
        { p: "forward", n: 1 },
        { p: "", n: 2 },
        { p: "goalkeeper", n: 3 },
      ],
      (i) => i.p,
    );
    expect(groups.map((g) => [g.label, g.items.length])).toEqual([
      ["Gardiens", 1],
      ["Attaquants", 1],
      ["Sans poste", 1],
    ]);
  });
});
