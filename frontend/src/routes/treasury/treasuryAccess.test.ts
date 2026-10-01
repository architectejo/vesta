import { describe, expect, it } from "vitest";
import { getTreasuryAccess } from "./treasuryAccess";

describe("getTreasuryAccess (TEMPORAIRE, en attendant les capacités de l'API)", () => {
  it("n'accorde rien tant que les rôles ne sont pas connus", () => {
    expect(getTreasuryAccess(undefined)).toEqual({ canRead: false, canWrite: false });
    expect(getTreasuryAccess([])).toEqual({ canRead: false, canWrite: false });
  });

  it.each(["president", "treasurer"])("accorde lecture et écriture à %s", (role) => {
    expect(getTreasuryAccess([{ role }])).toEqual({ canRead: true, canWrite: true });
  });

  it.each(["vice_president", "assistant_treasurer"])("accorde la lecture seule à %s", (role) => {
    expect(getTreasuryAccess([{ role }])).toEqual({ canRead: true, canWrite: false });
  });

  it.each(["coach", "captain", "doctor", "steward", "sports_director"])("refuse %s", (role) => {
    expect(getTreasuryAccess([{ role }])).toEqual({ canRead: false, canWrite: false });
  });

  it("cumule les rôles d'un même joueur", () => {
    expect(getTreasuryAccess([{ role: "coach" }, { role: "treasurer" }])).toEqual({
      canRead: true,
      canWrite: true,
    });
  });
});
