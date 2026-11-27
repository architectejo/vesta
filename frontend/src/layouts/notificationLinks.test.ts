import { describe, expect, it } from "vitest";
import { resolveNotificationRoute } from "./notificationLinks";

type Ctx = { isPaymentRecorder: boolean; isCoach?: boolean; isTreasuryViewer?: boolean; isSuperuser?: boolean };
const player: Ctx = { isPaymentRecorder: false };
const recorder: Ctx = { isPaymentRecorder: true };

function route(linkObjectType: string, linkObjectId: number | null, eventType = "", ctx: Ctx = player) {
  return resolveNotificationRoute({ eventType, linkObjectType, linkObjectId }, ctx);
}

describe("resolveNotificationRoute", () => {
  it("relie les types qui ont un écran atteignable", () => {
    expect(route("Match", 7)).toBe("/matchs/7");
    expect(route("TacticalPlan", 3, "", { isPaymentRecorder: false, isCoach: true })).toBe("/plans/3/tableau");
    expect(route("TacticalPlan", 3)).toBe("/vestiaire?onglet=plans&plan=3");
    expect(route("MembershipApplication", 12)).toBe("/club/comite?adhesion=12");
    expect(route("Membership", 4)).toBe("/club/comite");
    expect(route("Expense", 9)).toBe("/tresorerie/depenses?depense=9");
    expect(route("SocialAssistanceRequest", 2)).toBe("/tresorerie/assistance?demande=2");
    expect(route("Assembly", 5)).toBe("/club/assemblees?assemblee=5");
    expect(route("Post", 8)).toBe("/fil?publication=8");
    expect(route("Announcement", 6)).toBe("/club/communiques?communique=6");
    expect(route("Injury", 1)).toBe("/medical");
    expect(route("TransferOffer", 1)).toBe("/mercato");
    expect(route("MercatoThread", 1)).toBe("/mercato");
    expect(route("Inventory", 3)).toBe("/materiel?inventaire=3");
  });

  it("mène l'incitation du chat (sans objet lié) à la carte « Situation financière » du profil", () => {
    expect(route("", null, "chat_members_in_order_incentive")).toBe("/profil#situation-financiere");
    expect(route("", null, "chat_members_in_order_incentive", recorder)).toBe("/profil#situation-financiere");
  });

  it("oriente un paiement selon le destinataire", () => {
    expect(route("Payment", 4, "payment_validated")).toBe("/profil?paiement=4");
    expect(route("Payment", 4, "i_paid_declared", recorder)).toBe("/tresorerie?paiement=4");
    expect(route("Payment", 4, "i_paid_declared", player)).toBe("/profil?declaration=4");
  });

  it("oriente une déclaration refusée vers le profil, quel que soit le rôle", () => {
    expect(route("Payment", 4, "i_paid_rejected")).toBe("/profil?declaration=4");
    expect(route("Payment", 4, "i_paid_rejected", recorder)).toBe("/profil?declaration=4");
  });

  it("oriente une dette constatée selon le rôle", () => {
    expect(route("Due", 5, "due_created")).toBe("/profil");
    expect(route("Due", 5, "due_created", { isPaymentRecorder: true, isTreasuryViewer: true })).toBe("/tresorerie");
    expect(route("Due", null, "due_created", { isPaymentRecorder: false, isTreasuryViewer: true })).toBe("/tresorerie");
  });

  it("relie une séance créée à sa page", () => {
    expect(route("Session", 11)).toBe("/seances/11");
  });

  it("renvoie null pour un type sans écran ou inconnu", () => {
    expect(route("Licence", 1)).toBeNull();
    expect(route("LedgerChainState", 1)).toBeNull();
    expect(route("Incident", 1)).toBeNull();
    expect(route("", null)).toBeNull();
    expect(route("Match", null)).toBeNull();
  });

  it("laisse sans destination les types sans écran atteignable", () => {
    expect(route("Licence", 4, "licence_expiring")).toBeNull();
    expect(route("Licence", 4, "licence_expiring", { isPaymentRecorder: false, isTreasuryViewer: true })).toBeNull();
    expect(route("Incident", 5, "card_or_suspension")).toBeNull();
    expect(route("LedgerChainState", 1)).toBeNull();
  });

  it("ne mène pas un Superuser vers le fil de l'espace club", () => {
    expect(route("Post", 8, "post_reported")).toBeNull();
    expect(route("Post", 8, "post_reported", { isPaymentRecorder: false, isSuperuser: true })).toBeNull();
    expect(route("Post", 8, "", { isPaymentRecorder: false, isSuperuser: true })).toBeNull();
    expect(route("Post", null, "post_reported")).toBeNull();
    expect(route("Post", 8, "post_commented")).toBe("/fil?publication=8");
  });
});
