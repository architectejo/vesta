import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "../../../design-system";
import { availabilityBadge } from "./playerCardFormat";

describe("availabilityBadge — libellé de l'API affiché tel quel (CDC 10.3 n° 188)", () => {
  it("dette vue par le Coach : « Non éligible. » de l'API, jamais remplacé par « Indisponible »", () => {
    const badge = availabilityBadge({ label: "Non éligible.", family: "unavailable" });
    expect(badge.label).toBe("Non éligible.");
    render(<StatusBadge status={badge.status} detail={badge.detail} label={badge.label} />);
    expect(screen.getByText("Non éligible.")).toBeInTheDocument();
    expect(screen.queryByText(/Indisponible/)).not.toBeInTheDocument();
    expect(screen.queryByText(/dette/i)).not.toBeInTheDocument();
  });

  it("libellé vide : repli sur le libellé gris de la clé", () => {
    const badge = availabilityBadge({ label: "  ", family: "unavailable" });
    render(<StatusBadge status={badge.status} label={badge.label} />);
    expect(screen.getByText("Indisponible")).toBeInTheDocument();
  });

  it("la couleur reste celle de la clé (gris)", () => {
    render(<StatusBadge status="medical_unavailable" label="Non éligible." />);
    expect(screen.getByText("Non éligible.").closest("span.rounded-full")?.className).toContain(
      "bg-status-neutral-bg",
    );
  });
});
