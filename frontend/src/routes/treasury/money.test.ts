import { describe, expect, it } from "vitest";
import { formatAmount, formatDateFr, formatMonthYear, formatNumber } from "./money";

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
