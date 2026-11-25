import { describe, expect, it } from "vitest";
import { SERIES_STYLES, formatAxisNumber, formatNumber, niceScale, visibleLabelIndexes, withUnit } from "./chartUtils";

describe("niceScale", () => {
  it("arrondit à une échelle ronde", () => {
    const scale = niceScale(0, 74, 4);
    expect(scale.min).toBe(0);
    expect(scale.max).toBe(80);
    expect(scale.ticks).toEqual([0, 20, 40, 60, 80]);
  });

  it("gère les valeurs toutes nulles", () => {
    const scale = niceScale(0, 0);
    expect(scale.max).toBeGreaterThan(0);
    expect(scale.ticks[0]).toBe(0);
  });

  it("gère une étendue nulle non nulle (un seul point)", () => {
    const scale = niceScale(74, 74);
    expect(scale.min).toBe(0);
    expect(scale.max).toBeGreaterThanOrEqual(74);
  });

  it("gère les grandes valeurs et les décimales sans erreur d'arrondi", () => {
    expect(niceScale(0, 1_234_567).max).toBe(1_500_000);
    expect(niceScale(0, 0.7, 4).ticks).toEqual([0, 0.2, 0.4, 0.6, 0.8]);
  });

  it("gère les valeurs négatives", () => {
    const scale = niceScale(-30, 50, 4);
    expect(scale.min).toBeLessThanOrEqual(-30);
    expect(scale.ticks).toContain(0);
  });
});

describe("formatage", () => {
  it("formate à la française et compacte les grandes valeurs d'axe", () => {
    expect(formatNumber(12.5)).toBe("12,5");
    expect(formatAxisNumber(1_200_000)).toMatch(/M/);
    expect(withUnit("74", "%")).toBe("74 %");
    expect(withUnit("74")).toBe("74");
  });
});

describe("visibleLabelIndexes", () => {
  it("garde toujours la dernière étiquette et espace les autres", () => {
    const shown = visibleLabelIndexes(10, 20, 40);
    expect(shown.has(9)).toBe(true);
    expect(shown.size).toBeLessThan(10);
  });
});

describe("SERIES_STYLES", () => {
  it("n'utilise que des variables CSS et des tracés tous différents", () => {
    for (const style of SERIES_STYLES) expect(style.color).toMatch(/^var\(--color-series-\d\)$/);
    expect(new Set(SERIES_STYLES.map((s) => s.dash)).size).toBe(SERIES_STYLES.length);
    expect(new Set(SERIES_STYLES.map((s) => s.pattern)).size).toBe(SERIES_STYLES.length);
  });
});
