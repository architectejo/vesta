import { describe, expect, it } from "vitest";
import type { TransferOffer } from "../../api/mercato";
import { STATUS_MAP } from "../../design-system/components/statusMap";
import { ORIGIN_AWAITING_QUITUS_DETAIL, buildTransferTimeline, offerStatusKey } from "./mercatoLabels";

const BASE: TransferOffer = {
  id: 1,
  status: "sent",
  origin_club: { id: 1, name: "Club A", logo: null },
  target_club: { id: 2, name: "Club B", logo: null },
  player: {
    membership_id: 10,
    first_name: "Jean",
    last_name: "Kabila",
    photo: null,
    position: "midfielder",
    position_label: "Milieu",
    jersey_number: 8,
    age: 24,
    club: { id: 1, name: "Club A", logo: null },
    average_rating: "7.5",
    is_on_transfer_market: true,
  },
  message: "Venez nous rejoindre.",
  conditions: "",
  membership_fee_due_at_target: true,
  debt_amount: null,
  debt_checked_at: null,
  player_decision_at: null,
  quitus_available: false,
  completed_at: null,
  created_at: "2026-03-12T10:00:00Z",
};

const LABELS = { responseStepLabel: "Votre réponse", verificationStepLabel: "Vérification de votre solde" };

describe("offerStatusKey", () => {
  it("l'API choisit la clé selon le club qui regarde ; l'interface ne recalcule jamais", () => {
    expect(offerStatusKey("sent")).toBe("transfer_pending");
    expect(offerStatusKey("accepted_by_player")).toBe("transfer_accepted");
    expect(offerStatusKey("declined_by_player")).toBe("transfer_refused");
    expect(offerStatusKey("blocked_debt")).toBe("transfer_blocked");
    expect(offerStatusKey("awaiting_quitus")).toBe("transfer_awaiting_quitus");
    expect(offerStatusKey("completed")).toBe("transfer_done");
    expect(offerStatusKey("cancelled")).toBe("transfer_cancelled");
  });
});

describe("buildTransferTimeline", () => {
  it("« En attente » : seule la première étape est faite, le reste à venir", () => {
    const steps = buildTransferTimeline(BASE, LABELS);
    expect(steps.map((s) => s.state)).toEqual(["done", "upcoming", "upcoming", "upcoming", "upcoming"]);
  });

  it("« Bloquée (dette) » : l'étape de vérification est bloquée avec le montant, jamais la couleur seule", () => {
    const offer: TransferOffer = {
      ...BASE,
      status: "blocked_debt",
      debt_amount: "20.00",
      player_decision_at: "2026-03-13T10:00:00Z",
    };
    const steps = buildTransferTimeline(offer, LABELS);
    const verification = steps.find((s) => s.key === "verification")!;
    expect(verification.state).toBe("blocked");
    expect(verification.detail).toContain("20.00");
  });

  it("« Quitus en attente » (vue du club offrant) : aucun montant dans le détail", () => {
    const offer: TransferOffer = { ...BASE, status: "awaiting_quitus", player_decision_at: "2026-03-13T10:00:00Z" };
    const steps = buildTransferTimeline(offer, LABELS);
    const verification = steps.find((s) => s.key === "verification")!;
    expect(verification.state).toBe("blocked");
    expect(verification.detail).not.toMatch(/\d/);
  });

  it("« Transfert effectué » : toutes les étapes sont faites et datées", () => {
    const offer: TransferOffer = {
      ...BASE,
      status: "completed",
      player_decision_at: "2026-03-13T10:00:00Z",
      completed_at: "2026-03-14T10:00:00Z",
    };
    const steps = buildTransferTimeline(offer, LABELS);
    expect(steps.every((s) => s.state === "done")).toBe(true);
  });

  it("« Refusée » : l'étape de réponse est bloquée, le reste reste à venir", () => {
    const offer: TransferOffer = { ...BASE, status: "declined_by_player", player_decision_at: "2026-03-13T10:00:00Z" };
    const steps = buildTransferTimeline(offer, LABELS);
    expect(steps.find((s) => s.key === "response")!.state).toBe("blocked");
    expect(steps.find((s) => s.key === "quitus")!.state).toBe("upcoming");
  });
});

describe("offre bloquée vue du club d'origine sans accès aux finances (CDC 10.3 n° 188 et 192)", () => {
  const FORBIDDEN = /dette|régularis|solde|financi|\d+[.,]\d{2}/i;
  // Contrat de l'API : DS, Coach et Assistant du Coach du club A reçoivent
  // `awaiting_quitus`, sans montant ni date de vérification.
  const originNeutral: TransferOffer = {
    ...BASE,
    status: "awaiting_quitus",
    debt_amount: null,
    debt_checked_at: null,
    player_decision_at: "2026-03-13T10:00:00Z",
  };

  it("badge « Quitus en attente », jamais « Bloquée (dette) »", () => {
    const key = offerStatusKey(originNeutral.status);
    expect(key).toBe("transfer_awaiting_quitus");
    expect(STATUS_MAP[key].label).not.toMatch(FORBIDDEN);
  });

  it("club A : texte neutre, sans « dette », « régulariser », « solde » ni montant", () => {
    const steps = buildTransferTimeline(originNeutral, {
      responseStepLabel: "Réponse du joueur",
      verificationStepLabel: "Vérification auprès de Club A",
      viewerIsOriginClub: true,
    });
    const verification = steps.find((s) => s.key === "verification")!;
    expect(verification.detail).toBe(ORIGIN_AWAITING_QUITUS_DETAIL);
    const text = steps.map((s) => `${s.label} ${s.detail ?? ""}`).join(" ");
    expect(text).not.toMatch(FORBIDDEN);
    expect(text).not.toContain("son club actuel");
  });

  it("club B : texte inchangé « En attente du quitus de son club actuel », sans montant", () => {
    const steps = buildTransferTimeline(originNeutral, LABELS);
    const verification = steps.find((s) => s.key === "verification")!;
    expect(verification.detail).toBe("En attente du quitus de son club actuel");
    expect(verification.detail).not.toMatch(/\d/);
  });

  it("« Bloquée (dette) » sans montant : aucun motif financier recomposé par l'interface", () => {
    const steps = buildTransferTimeline({ ...originNeutral, status: "blocked_debt" }, LABELS);
    const verification = steps.find((s) => s.key === "verification")!;
    expect(verification.state).toBe("blocked");
    expect(verification.detail).toBeUndefined();
  });

  it("valeur inconnue de l'API : affichage neutre, jamais « Transfert effectué » ni motif recomposé", () => {
    const unknown = { ...originNeutral, status: "something_new" } as unknown as TransferOffer;
    expect(offerStatusKey(unknown.status)).toBe("transfer_pending");
    const steps = buildTransferTimeline(unknown, LABELS);
    expect(steps.find((s) => s.key === "done")!.state).toBe("upcoming");
    expect(steps.some((s) => FORBIDDEN.test(s.detail ?? ""))).toBe(false);
  });

  it("offre annulée : les étapes suivantes ne sont pas marquées faites", () => {
    const steps = buildTransferTimeline({ ...originNeutral, status: "cancelled" }, LABELS);
    expect(steps.find((s) => s.key === "done")!.state).toBe("upcoming");
  });
});
