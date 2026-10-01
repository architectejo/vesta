import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DesignSystemDemoPage } from "./DesignSystemDemo";

describe("DesignSystemDemoPage", () => {
  it("affiche la page de démonstration sans erreur, avec ses sections principales", () => {
    render(<DesignSystemDemoPage />);

    expect(
      screen.getByRole("heading", { name: "Design system Vesta — démonstration interne" }),
    ).toBeInTheDocument();

    // StatusBadge : quelques libellés de la correspondance complète (peuvent
    // apparaître plusieurs fois, notamment dans les lignes de DataTable).
    expect(screen.getAllByText("En dette").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Suspendu").length).toBeGreaterThan(0);

    // DataTable : ligne de résultats du jeu de données fictif (34 lignes).
    expect(screen.getByText("34 joueurs")).toBeInTheDocument();

    // Sidebar : nom de club fictif lu depuis le contexte, jamais en dur.
    expect(screen.getAllByText("Club fictif de démonstration").length).toBeGreaterThan(0);

    // Footer : texte exact et unique.
    expect(
      screen.getByText(
        "VESTA by IMARA TECH Group — une partie de nos revenus est destinée aux orphelinats locaux",
      ),
    ).toBeInTheDocument();
  });
});
