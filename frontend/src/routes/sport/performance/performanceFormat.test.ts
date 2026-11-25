import { describe, expect, it } from "vitest";
import {
  describeFields,
  formatStopwatch,
  formatTimeMs,
  fromHundredths,
  indicativeSpeedKmh,
  parseCount,
  parseDecimalString,
  parseTimeToMs,
  toHundredths,
} from "./performanceFormat";

describe("performanceFormat", () => {
  it("formate le chrono au centième, tronqué", () => {
    expect(formatStopwatch(0)).toBe("00:00,00");
    expect(formatStopwatch(4379)).toBe("00:04,37");
    expect(formatStopwatch(65_300)).toBe("01:05,30");
  });

  it("formate un temps figé comme l'API", () => {
    expect(formatTimeMs(4520)).toBe("4,52 s");
    expect(formatTimeMs(65_300)).toBe("1 min 05,30 s");
  });

  it("calcule la vitesse indicative (distance ÷ temps) et rien si les données manquent", () => {
    expect(indicativeSpeedKmh("30.00", 4520)).toMatch(/^23,9\s+km\/h$/);
    expect(indicativeSpeedKmh(null, 4520)).toBeNull();
    expect(indicativeSpeedKmh("30", 0)).toBeNull();
  });

  it("lit un temps en millisecondes ENTIÈRES, sans flottant", () => {
    expect(parseTimeToMs("4,52")).toBe(4520);
    expect(parseTimeToMs("4.5")).toBe(4500);
    expect(parseTimeToMs("1:05,30")).toBe(65_300);
    expect(parseTimeToMs("0,1")).toBe(100);
    expect(parseTimeToMs("4,525")).toBe(4525);
    expect(Number.isInteger(parseTimeToMs("19,99"))).toBe(true);
    expect(parseTimeToMs("19,99")).toBe(19_990);
  });

  it("refuse les temps invalides ou nuls", () => {
    expect(parseTimeToMs("")).toBeNull();
    expect(parseTimeToMs("0")).toBeNull();
    expect(parseTimeToMs("abc")).toBeNull();
    expect(parseTimeToMs("1:75")).toBeNull();
    expect(parseTimeToMs("4,5252")).toBeNull();
  });

  it("lit les décimales françaises en chaîne pour l'API", () => {
    expect(parseDecimalString("2 650,5")).toBe("2650.5");
    expect(parseDecimalString("12")).toBe("12");
    expect(parseDecimalString("1,234")).toBeNull();
    expect(parseDecimalString("-3")).toBeNull();
  });

  it("lit un entier de répétitions", () => {
    expect(parseCount("7")).toBe(7);
    expect(parseCount("7,5")).toBeNull();
    expect(parseCount("")).toBeNull();
  });

  it("calcule en centièmes entiers pour les tours", () => {
    expect(toHundredths("400.5")).toBe(40_050);
    expect(fromHundredths(6 * 40_000 + 5_000)).toBe("2450");
    expect(fromHundredths(12_050)).toBe("120.5");
  });

  it("décrit une mesure en attente", () => {
    const test = { attempts: 10, unit_label: "points" };
    expect(describeFields(test, { outcome: "dnf" })).toBe("Abandon");
    expect(describeFields(test, { time_ms: 4520 })).toBe("4,52 s");
    expect(describeFields(test, { count: 7 })).toBe("7 sur 10");
  });
});
