import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Banner } from "./Banner";

describe("Banner", () => {
  it("affiche le message et utilise role=alert pour danger", () => {
    render(<Banner variant="danger">Une dépense n'est pas justifiée.</Banner>);
    expect(screen.getByRole("alert")).toHaveTextContent("Une dépense n'est pas justifiée.");
  });

  it("affiche role=status pour les autres variantes", () => {
    render(<Banner variant="info">Vous êtes hors connexion.</Banner>);
    expect(screen.getByRole("status")).toHaveTextContent("Vous êtes hors connexion.");
  });
});
