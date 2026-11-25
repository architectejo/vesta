import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChartCard } from "./ChartCard";

describe("ChartCard", () => {
  it("affiche titre, période, chiffre clé, phrase de lecture et contenu", () => {
    render(
      <ChartCard title="Présences" periodLabel="novembre 2026" value="74 %" caption="Dernière séance 72 %" onOpen={() => undefined}>
        <p>graphique</p>
      </ChartCard>,
    );
    expect(screen.getByRole("heading", { name: "Présences", level: 3 })).toBeInTheDocument();
    expect(screen.getByText("novembre 2026")).toBeInTheDocument();
    expect(screen.getByText("74 %")).toBeInTheDocument();
    expect(screen.getByText("Dernière séance 72 %")).toBeInTheDocument();
    expect(screen.getByText("graphique")).toBeInTheDocument();
  });

  it("ouvre le détail au clic et au clavier (Entrée, Espace)", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<ChartCard title="Cotisations" onOpen={onOpen} />);
    const button = screen.getByRole("button", { name: "Voir le détail : Cotisations" });
    expect(button.className).toContain("before:inset-0");
    await user.click(button);
    button.focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    expect(onOpen).toHaveBeenCalledTimes(3);
  });

  it("n'affiche pas de bouton sans onOpen", () => {
    render(<ChartCard title="Cotisations" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("chargement : squelette annoncé, carte occupée, pas de bouton", async () => {
    render(<ChartCard title="Caisse" state="loading" onOpen={() => undefined} />);
    expect(await screen.findByText("Chargement…")).toBeInTheDocument();
    expect(screen.getByRole("article")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("vide : EmptyState avec le message fourni", () => {
    render(<ChartCard title="Résultats" state="empty" emptyMessage="Aucun match joué sur la période." />);
    expect(screen.getByText("Aucun match joué sur la période.")).toBeInTheDocument();
  });

  it("erreur : message et « Réessayer »", async () => {
    const onRetry = vi.fn();
    render(<ChartCard title="Discipline" state="error" errorMessage="Impossible de charger la discipline." onRetry={onRetry} />);
    expect(screen.getByText("Impossible de charger la discipline.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("garde le contenu interactif au-dessus de la zone tactile de la carte", () => {
    render(
      <ChartCard title="Présences" interactiveContent onOpen={() => undefined}>
        <button type="button">Point</button>
      </ChartCard>,
    );
    expect(screen.getByRole("button", { name: "Point" }).parentElement?.className).toContain("z-10");
  });
});
