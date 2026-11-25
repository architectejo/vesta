import { afterEach, describe, expect, it } from "vitest";
import {
  clearSessionTokens,
  getAccessToken,
  getRefreshToken,
  getStoredIdentity,
  hasSession,
  setSessionTokens,
  setStoredIdentity,
} from "./session";

const IDENTITY = {
  user: {
    id: 1,
    email: "j@example.com",
    first_name: "Jean",
    last_name: "K.",
    is_superuser: false,
    must_change_password: true,
    preferred_theme: "classic",
  },
  club: null,
};

describe("session (CDC 7.4 : session propre à chaque onglet)", () => {
  afterEach(() => {
    clearSessionTokens();
  });

  it("stocke et relit les jetons dans sessionStorage (isolé par onglet)", () => {
    expect(hasSession()).toBe(false);
    setSessionTokens({ access: "a1", refresh: "r1" });
    expect(hasSession()).toBe(true);
    expect(getAccessToken()).toBe("a1");
    expect(getRefreshToken()).toBe("r1");
  });

  it("efface tout (jetons et identité) à la déconnexion", () => {
    setSessionTokens({ access: "a1", refresh: "r1" });
    setStoredIdentity(IDENTITY);
    clearSessionTokens();
    expect(getAccessToken()).toBeNull();
    expect(getStoredIdentity()).toBeNull();
  });

  it("conserve l'identité stockée telle quelle", () => {
    setStoredIdentity(IDENTITY);
    expect(getStoredIdentity()).toEqual(IDENTITY);
  });

  it.each([
    ["sans utilisateur", JSON.stringify({ club: null })],
    ["avec un utilisateur nul", JSON.stringify({ user: null, club: null })],
    ["qui n'est pas un objet", JSON.stringify("texte")],
    ["illisible", "{pas du json"],
  ])("traite comme absente une identité stockée %s", (_label, raw) => {
    window.sessionStorage.setItem("vesta:identity", raw);
    expect(getStoredIdentity()).toBeNull();
  });
});
