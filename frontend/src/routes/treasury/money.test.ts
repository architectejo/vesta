import { describe, expect, it } from "vitest";
import { formatAmount, formatDateFr, formatMonthYear, formatNumber, isPositiveAmount, toApiAmount } from "./money";

describe("formatNumber", () => {
  it("masque les décimales nulles", () => {
    expect(formatNumber("20.00")).toBe("20");
  });

  it("garde les décimales non nulles", () => {
    expect(formatNumber("5.50")).toBe("5,50");
  });
});

describe("formatAmount", () => {
  it("ajoute la devise après le montant", () => {
    expect(formatAmount("20.00", "USD")).toBe("20 USD");
  });
});

describe("formatDateFr", () => {
  it("formate une date ISO en jj/mm/aaaa", () => {
    expect(formatDateFr("2026-03-05")).toBe("05/03/2026");
  });
});

describe("formatMonthYear", () => {
  it("formate un mois en toutes lettres", () => {
    expect(formatMonthYear("2026-03-01")).toBe("mars 2026");
  });
});

describe("toApiAmount", () => {
  it("remplace la virgule par un point et retire les espaces de bord", () => {
    expect(toApiAmount(" 10,50 ")).toBe("10.50");
    expect(toApiAmount("10.50")).toBe("10.50");
  });

  it("ne transforme pas autrement la saisie (l'API valide)", () => {
    expect(toApiAmount("1e3")).toBe("1e3");
    expect(toApiAmount("1 000")).toBe("1 000");
  });
});

describe("isPositiveAmount", () => {
  it("accepte virgule et point, refuse vide, zéro et texte", () => {
    expect(isPositiveAmount("10,50")).toBe(true);
    expect(isPositiveAmount("10.5")).toBe(true);
    expect(isPositiveAmount("")).toBe(false);
    expect(isPositiveAmount("0,00")).toBe(false);
    expect(isPositiveAmount("abc")).toBe(false);
  });
});
