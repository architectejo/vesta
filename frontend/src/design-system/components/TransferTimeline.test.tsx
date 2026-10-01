import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TransferTimeline, type TransferTimelineStep } from "./TransferTimeline";

describe("TransferTimeline", () => {
  it("affiche le libellé et la date de chaque étape", () => {
    const steps: TransferTimelineStep[] = [
      { key: "offer", label: "Offre reçue", state: "done", date: "12/03/2026" },
      { key: "response", label: "Votre réponse", state: "upcoming" },
    ];
    render(<TransferTimeline steps={steps} />);
    expect(screen.getByText(/Offre reçue/)).toBeInTheDocument();
    expect(screen.getByText(/12\/03\/2026/)).toBeInTheDocument();
    expect(screen.getByText("Votre réponse")).toBeInTheDocument();
  });

  it("affiche l'explication d'une étape bloquée, jamais la couleur seule", () => {
    const steps: TransferTimelineStep[] = [
      {
        key: "verification",
        label: "Vérification de votre solde",
        state: "blocked",
        detail: "Bloquée : En dette : 20 $",
      },
    ];
    render(<TransferTimeline steps={steps} />);
    expect(screen.getByText("Vérification de votre solde")).toBeInTheDocument();
    expect(screen.getByText("Bloquée : En dette : 20 $")).toBeInTheDocument();
  });

  it("affiche l'explication d'une étape en cours", () => {
    const steps: TransferTimelineStep[] = [
      { key: "verification", label: "Vérification", state: "current", detail: "Vérification en cours…" },
    ];
    render(<TransferTimeline steps={steps} />);
    expect(screen.getByText("Vérification en cours…")).toBeInTheDocument();
  });
});
