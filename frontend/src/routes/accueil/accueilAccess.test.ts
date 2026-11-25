import { describe, expect, it } from "vitest";
import { getAccueilAccess } from "./accueilAccess";

describe("getAccueilAccess", () => {
  it("autorise le Président à publier un communiqué et marque isPresident", () => {
    const access = getAccueilAccess([{ role: "president" }]);
    expect(access.canPublishAnnouncement).toBe(true);
    expect(access.isPresident).toBe(true);
  });

  it("autorise le Vice-président à publier un communiqué sans être Président", () => {
    const access = getAccueilAccess([{ role: "vice_president" }]);
    expect(access.canPublishAnnouncement).toBe(true);
    expect(access.isPresident).toBe(false);
  });

  it("refuse la publication à un simple joueur", () => {
    const access = getAccueilAccess([{ role: "member" }]);
    expect(access.canPublishAnnouncement).toBe(false);
    expect(access.isPresident).toBe(false);
  });

  it("ne plante pas sans rôle connu", () => {
    const access = getAccueilAccess(undefined);
    expect(access.canPublishAnnouncement).toBe(false);
    expect(access.isPresident).toBe(false);
  });
});

describe("getAccueilAccess : Secretaire", () => {
  it("autorise le Secretaire a publier un communique sans etre President", () => {
    const access = getAccueilAccess([{ role: "secretary" }]);
    expect(access.canPublishAnnouncement).toBe(true);
    expect(access.isPresident).toBe(false);
  });
});
