import { describe, expect, it } from "vitest";
import { combineDateTimeToIso, formatTime, nowTimeHHMM, todayIsoDate } from "./sportTime";

describe("formatTime", () => {
  it("renvoie une chaîne vide sans heure", () => {
    expect(formatTime(null)).toBe("");
  });

  it("formate une heure ISO en HH:mm", () => {
    const iso = new Date(2026, 8, 27, 7, 42).toISOString();
    expect(formatTime(iso)).toMatch(/^\d{2}:\d{2}$/);
  });

  it("affiche l'heure dans le fuseau du club, pas celui du téléphone (CLAUDE.md §7)", () => {
    const iso = "2026-11-26T14:05:00Z";
    expect(formatTime(iso, "Africa/Kinshasa")).toBe("15:05");
    expect(formatTime(iso, "Asia/Tokyo")).toBe("23:05");
    expect(formatTime(iso, "America/New_York")).toBe("09:05");
  });

  it("fuseau inconnu : retombe sur le fuseau du téléphone sans planter", () => {
    expect(formatTime("2026-11-26T14:05:00Z", "Pas/UnFuseau")).toMatch(/^\d{2}:\d{2}$/);
  });
});

describe("combineDateTimeToIso", () => {
  it("interprète la date et l'heure saisies à l'heure du club", () => {
    expect(combineDateTimeToIso("2026-11-26", "15:05", "Africa/Kinshasa")).toBe("2026-11-26T14:05:00.000Z");
    expect(combineDateTimeToIso("2026-11-26", "08:30", "Asia/Tokyo")).toBe("2026-11-25T23:30:00.000Z");
  });

  it("tombe juste autour d'un changement d'heure", () => {
    // New York passe à l'heure d'été le 8 mars 2026 à 2 h (UTC-5 → UTC-4).
    expect(combineDateTimeToIso("2026-03-07", "10:00", "America/New_York")).toBe("2026-03-07T15:00:00.000Z");
    expect(combineDateTimeToIso("2026-03-09", "10:00", "America/New_York")).toBe("2026-03-09T14:00:00.000Z");
  });

  it("aller-retour : l'heure saisie est celle réaffichée", () => {
    const iso = combineDateTimeToIso("2026-11-26", "07:42", "Asia/Tokyo");
    expect(formatTime(iso, "Asia/Tokyo")).toBe("07:42");
  });
});

describe("todayIsoDate / nowTimeHHMM", () => {
  it("donnent le jour et l'heure du club", () => {
    const now = new Date("2026-11-26T23:30:00Z");
    expect(todayIsoDate("Africa/Kinshasa", now)).toBe("2026-11-27");
    expect(todayIsoDate("America/New_York", now)).toBe("2026-11-26");
    expect(nowTimeHHMM("Africa/Kinshasa", now)).toBe("00:30");
    expect(nowTimeHHMM("Asia/Tokyo", now)).toBe("08:30");
  });
});
