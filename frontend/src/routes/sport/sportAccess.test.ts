import { describe, expect, it } from "vitest";
import { getSportAccess } from "./sportAccess";

describe("getSportAccess", () => {
  it("donne au Coach tous les droits d'écriture sportifs", () => {
    const access = getSportAccess([{ role: "coach" }]);
    expect(access.canRecordAttendance).toBe(true);
    expect(access.canCorrectAttendanceTime).toBe(true);
    expect(access.canAssignTeams).toBe(true);
    expect(access.canManageMatch).toBe(true);
    expect(access.canRecordIncident).toBe(true);
    expect(access.canEvaluate).toBe(true);
    expect(access.canEditTacticalPlan).toBe(true);
  });

  it("limite le Capitaine au pointage, à la répartition et aux incidents", () => {
    const access = getSportAccess([{ role: "captain" }]);
    expect(access.canRecordAttendance).toBe(true);
    expect(access.canAssignTeams).toBe(true);
    expect(access.canRecordIncident).toBe(true);
    expect(access.canCorrectAttendanceTime).toBe(false);
    expect(access.canManageMatch).toBe(false);
    expect(access.canEvaluate).toBe(false);
    expect(access.canEditTacticalPlan).toBe(false);
  });

  it("ne donne aucun droit d'écriture à un simple joueur", () => {
    const access = getSportAccess([{ role: "member" }]);
    expect(access.canRecordAttendance).toBe(false);
    expect(access.canAssignTeams).toBe(false);
    expect(access.canManageMatch).toBe(false);
    expect(access.canEditTacticalPlan).toBe(false);
  });

  it("ne plante pas sans rôle connu", () => {
    const access = getSportAccess(undefined);
    expect(access.canRecordAttendance).toBe(false);
  });

  it("réserve la liste complète des blessures au Médecin, Coach, Président, VP, DS (pas le Capitaine)", () => {
    expect(getSportAccess([{ role: "doctor" }]).canSeeMedicalFull).toBe(true);
    expect(getSportAccess([{ role: "coach" }]).canSeeMedicalFull).toBe(true);
    expect(getSportAccess([{ role: "president" }]).canSeeMedicalFull).toBe(true);
    expect(getSportAccess([{ role: "vice_president" }]).canSeeMedicalFull).toBe(true);
    expect(getSportAccess([{ role: "sports_director" }]).canSeeMedicalFull).toBe(true);
    expect(getSportAccess([{ role: "captain" }]).canSeeMedicalFull).toBe(false);
  });

  it("autorise le Coach, le Capitaine et le Médecin à déclarer une blessure", () => {
    expect(getSportAccess([{ role: "coach" }]).canReportInjury).toBe(true);
    expect(getSportAccess([{ role: "captain" }]).canReportInjury).toBe(true);
    expect(getSportAccess([{ role: "doctor" }]).canReportInjury).toBe(true);
    expect(getSportAccess([{ role: "member" }]).canReportInjury).toBe(false);
  });
});

describe("getSportAccess - Assistant du Coach", () => {
  it("donne à l'Assistant du Coach exactement les mêmes droits que le Coach", () => {
    expect(getSportAccess([{ role: "assistant_coach" }])).toEqual(getSportAccess([{ role: "coach" }]));
    expect(getSportAccess([{ role: "assistant_coach" }]).isCoach).toBe(true);
  });
});
