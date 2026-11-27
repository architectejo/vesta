import { describe, expect, it } from "vitest";
import { historyAttendanceLabel } from "./statsFormat";

describe("historyAttendanceLabel (page Entraînements, historique des séances)", () => {
  it("se fonde sur `marked` servi par l'API : séance non pointée", () => {
    expect(historyAttendanceLabel({ marked: false, present: 0, attendance_rate: null })).toBe("Non pointée");
  });

  it("séance pointée : présents et taux", () => {
    expect(historyAttendanceLabel({ marked: true, present: 9, attendance_rate: 75 })).toBe("9 présents · 75 %");
    expect(historyAttendanceLabel({ marked: true, present: 1, attendance_rate: 10 })).toBe("1 présent · 10 %");
  });

  it("séance pointée sans taux (aucun attendu) : jamais « Non pointée »", () => {
    expect(historyAttendanceLabel({ marked: true, present: 3, attendance_rate: null })).toBe("3 présents");
  });

  it("`marked` prime sur le taux : une séance déclarée non pointée l'est même avec un taux", () => {
    expect(historyAttendanceLabel({ marked: false, present: 0, attendance_rate: 0 })).toBe("Non pointée");
  });

  it("repli sur l'ancien test quand l'API ne sert pas encore `marked`", () => {
    expect(historyAttendanceLabel({ present: 0, attendance_rate: null })).toBe("Non pointée");
    expect(historyAttendanceLabel({ present: 4, attendance_rate: 50 })).toBe("4 présents · 50 %");
  });
});
