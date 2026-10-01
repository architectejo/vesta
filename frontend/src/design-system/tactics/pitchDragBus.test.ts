import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { pitchDragBus } from "./pitchDragBus";

describe("pitchDragBus — filet de sécurité au niveau de la fenêtre", () => {
  // jsdom n'implémente pas document.elementFromPoint (utilisé par
  // PitchDragBus.end pour résoudre la zone de dépose) : sans substitut, tout
  // appel à .end() lève, y compris ici où seule la fin du blocage importe.
  beforeAll(() => {
    document.elementFromPoint = () => null;
  });

  afterEach(() => {
    pitchDragBus.cancel();
  });

  it("relâcher le pointeur n'importe où dans la fenêtre termine un glissement bloqué (élément capturé disparu du DOM)", () => {
    pitchDragBus.start({ kind: "team-A-member", data: { membershipId: 1 }, label: "Jean K." }, 10, 10);
    expect(pitchDragBus.getSnapshot().dragging).not.toBeNull();

    window.dispatchEvent(new MouseEvent("pointerup", { clientX: 42, clientY: 42 }));

    expect(pitchDragBus.getSnapshot().dragging).toBeNull();
  });

  it("une perte de focus de la fenêtre (changement d'onglet, capture d'écran) annule un glissement bloqué", () => {
    pitchDragBus.start({ kind: "team-A-member", data: { membershipId: 1 }, label: "Jean K." }, 10, 10);
    expect(pitchDragBus.getSnapshot().dragging).not.toBeNull();

    window.dispatchEvent(new Event("blur"));

    expect(pitchDragBus.getSnapshot().dragging).toBeNull();
  });

  it("un pointercancel natif annule un glissement bloqué", () => {
    pitchDragBus.start({ kind: "team-A-member", data: { membershipId: 1 }, label: "Jean K." }, 10, 10);

    window.dispatchEvent(new Event("pointercancel"));

    expect(pitchDragBus.getSnapshot().dragging).toBeNull();
  });

  it("ne fait rien si aucun glissement n'est en cours (pas d'effet de bord en usage normal)", () => {
    expect(pitchDragBus.getSnapshot().dragging).toBeNull();
    window.dispatchEvent(new MouseEvent("pointerup", { clientX: 1, clientY: 1 }));
    window.dispatchEvent(new Event("blur"));
    expect(pitchDragBus.getSnapshot().dragging).toBeNull();
  });
});
