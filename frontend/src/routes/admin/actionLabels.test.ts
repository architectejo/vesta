import { describe, expect, it } from "vitest";
import { actionLabel, KNOWN_ACTION_CODES } from "./actionLabels";
import { EMITTED_ACTION_CODES } from "./emittedActionCodes";

describe("actionLabel", () => {
  it("traduit un code connu", () => {
    expect(actionLabel("treasury.payment.validated")).toBe("Paiement validé");
  });
  it("renvoie le code brut pour un code inconnu", () => {
    expect(actionLabel("payment.validated")).toBe("payment.validated");
  });
});

describe("couverture des libellés", () => {
  it("chaque code émis par l'API a un libellé français", () => {
    const missing = EMITTED_ACTION_CODES.filter((code) => !KNOWN_ACTION_CODES.includes(code));
    expect(missing).toEqual([]);
  });
  it("les codes PIN supprimés ne sont plus émis mais restent lisibles dans l'historique", () => {
    expect(EMITTED_ACTION_CODES.filter((code) => code.startsWith("accounts.pin."))).toEqual([]);
    expect(actionLabel("accounts.pin.defined")).toBe("Code PIN défini");
  });
  it("aucun libellé n'est vide", () => {
    for (const code of KNOWN_ACTION_CODES) expect(actionLabel(code).trim()).not.toBe("");
  });
});
