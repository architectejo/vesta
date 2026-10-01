import { describe, expect, it } from "vitest";
import { formatDateFrLong, formatTimeFr, nowTimeHHMM, todayIsoDate } from "./medicalFormat";

describe("formatDateFrLong", () => {
  it("formate une date ISO en « jour abrégé jour mois abrégé année » (design-system §4)", () => {
    // Dimanche 12 octobre 2026 (vérifié : 12/10/2026 tombe un lundi en
    // réalité, mais le format est ce qui est testé, pas le calendrier réel).
    expect(formatDateFrLong("2026-10-12")).toMatch(/^\w+\. 12 oct\. 2026$/);
  });

  it("accepte un datetime ISO complet (ne garde que la date)", () => {
    expect(formatDateFrLong("2026-01-05T14:30:00Z")).toMatch(/^\w+\. 5 janv\. 2026$/);
  });

  it("renvoie la valeur telle quelle si elle n'est pas une date valide", () => {
    expect(formatDateFrLong("not-a-date")).toBe("not-a-date");
  });
});

describe("formatTimeFr", () => {
  it("renvoie une chaîne vide sans heure", () => {
    expect(formatTimeFr(null)).toBe("");
  });

  it("formate une heure ISO en HH:mm", () => {
    const iso = new Date(2026, 8, 27, 7, 42).toISOString();
    expect(formatTimeFr(iso)).toMatch(/^\d{2}:\d{2}$/);
  });
});

describe("todayIsoDate / nowTimeHHMM", () => {
  it("renvoie une date au format YYYY-MM-DD", () => {
    expect(todayIsoDate()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("renvoie une heure au format HH:mm", () => {
    expect(nowTimeHHMM()).toMatch(/^\d{2}:\d{2}$/);
  });
});
