import { describe, expect, it } from "vitest";
import { getArchivesAccess } from "./archivesAccess";

describe("getArchivesAccess", () => {
  it("donne lecture et écriture au Secrétaire, au Président et au VP", () => {
    for (const role of ["secretary", "president", "vice_president"]) {
      expect(getArchivesAccess([{ role }])).toEqual({ canRead: true, canWrite: true });
    }
  });

  it("donne la lecture seule aux autres membres du Bureau", () => {
    for (const role of ["sports_director", "treasurer", "assistant_treasurer", "steward"]) {
      expect(getArchivesAccess([{ role }])).toEqual({ canRead: true, canWrite: false });
    }
  });

  it("refuse tout au Médecin, au Coach, au Capitaine et au simple joueur", () => {
    for (const role of ["doctor", "coach", "captain", "member"]) {
      expect(getArchivesAccess([{ role }])).toEqual({ canRead: false, canWrite: false });
    }
  });

  it("ne plante pas sans rôles", () => {
    expect(getArchivesAccess(undefined)).toEqual({ canRead: false, canWrite: false });
  });
});
