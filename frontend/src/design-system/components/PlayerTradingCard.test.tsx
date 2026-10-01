import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PlayerTradingCard } from "./PlayerTradingCard";
import { ClubBrandingProvider, type ClubBranding } from "../context/ClubBrandingContext";
import { ThemeProvider, type ThemeName } from "../context/ThemeContext";

const LONG_NAME_FIRST = "Jean-Baptiste-Emmanuel"; // avec le nom, atteint ~40 caractères
const LONG_NAME_LAST = "Nkulu-Mwamba-Ilunga";

// Couleurs synthétiques (donnée de test, jamais dans le code, CLAUDE.md §3).
const NAVY_RED_BRANDING: ClubBranding = {
  name: "Club de démonstration",
  logoUrl: null,
  primaryColor: "#1B2143",
  secondaryColor: "#D2232A",
};

function renderWithTheme(ui: React.ReactElement, theme: ThemeName, branding?: ClubBranding | null) {
  const tree = <ThemeProvider initialTheme={theme}>{ui}</ThemeProvider>;
  return render(
    branding ? <ClubBrandingProvider branding={branding}>{tree}</ClubBrandingProvider> : tree,
  );
}

describe("PlayerTradingCard", () => {
  it("affiche l'identité, le poste en toutes lettres et le numéro", () => {
    render(
      <PlayerTradingCard
        firstName="Aimé"
        lastName="Kalonji"
        positionLabel="Défenseur"
        jerseyNumber={4}
        motion="static"
      />,
    );
    expect(
      screen.getByRole("figure", { name: "Carte de joueur de Aimé Kalonji" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Aimé Kalonji")).toBeInTheDocument();
    expect(screen.getByText("Défenseur")).toBeInTheDocument();
    expect(screen.getByText("Numéro 4")).toBeInTheDocument();
    expect(screen.getByText("Statistiques à venir")).toBeInTheDocument();
  });

  it("n'abrège jamais le poste (jamais « DEF »)", () => {
    render(<PlayerTradingCard firstName="Aimé" lastName="Kalonji" positionLabel="Défenseur" motion="static" />);
    expect(screen.queryByText("DEF")).not.toBeInTheDocument();
    expect(screen.getByText("Défenseur")).toBeInTheDocument();
  });

  it("affiche « Poste non renseigné » quand le poste est vide", () => {
    render(<PlayerTradingCard firstName="Aimé" lastName="Kalonji" motion="static" />);
    expect(screen.getByText("Poste non renseigné")).toBeInTheDocument();
  });

  it("n'affiche pas de numéro quand jerseyNumber est null", () => {
    render(<PlayerTradingCard firstName="Aimé" lastName="Kalonji" jerseyNumber={null} motion="static" />);
    expect(screen.queryByText(/^Numéro/)).not.toBeInTheDocument();
  });

  it("affiche un nom de 40 caractères en entier, sans ellipse ni coupure (CDC 4.2)", () => {
    const fullName = `${LONG_NAME_FIRST} ${LONG_NAME_LAST}`;
    expect(fullName.length).toBeGreaterThanOrEqual(40);
    render(<PlayerTradingCard firstName={LONG_NAME_FIRST} lastName={LONG_NAME_LAST} motion="static" />);
    const nameNode = screen.getByText(fullName);
    expect(nameNode).toBeInTheDocument();
    expect(nameNode.className).not.toMatch(/truncate|ellipsis/);
  });

  it("affiche une silhouette quand aucune photo n'est fournie (aucune initiale en grand)", () => {
    render(<PlayerTradingCard firstName="Aimé" lastName="Kalonji" photoUrl={null} motion="static" />);
    expect(screen.getByRole("img", { name: "Photo de Aimé Kalonji" })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Photo de Aimé Kalonji" })?.tagName).not.toBe("IMG");
    expect(screen.queryByText("AK")).not.toBeInTheDocument();
  });

  it("bascule sur la silhouette si le chargement de la photo échoue", () => {
    render(
      <PlayerTradingCard
        firstName="Aimé"
        lastName="Kalonji"
        photoUrl="https://example.test/photo.jpg"
        motion="static"
      />,
    );
    const img = screen.getByRole("img", { name: "Photo de Aimé Kalonji" }) as HTMLImageElement;
    expect(img.tagName).toBe("IMG");
    act(() => {
      img.dispatchEvent(new Event("error"));
    });
    const fallback = screen.getByRole("img", { name: "Photo de Aimé Kalonji" });
    expect(fallback.tagName).not.toBe("IMG");
  });

  it("n'affiche aucune pastille de logo quand le club n'en a pas", () => {
    render(<PlayerTradingCard firstName="Aimé" lastName="Kalonji" clubLogoUrl={null} clubName="Club" motion="static" />);
    expect(screen.queryByRole("img", { name: /^Logo de/ })).not.toBeInTheDocument();
  });

  it("affiche le logo du club avec le texte alternatif attendu", () => {
    render(
      <PlayerTradingCard
        firstName="Aimé"
        lastName="Kalonji"
        clubLogoUrl="https://example.test/logo.png"
        clubName="Loisirs Club Discovery"
        motion="static"
      />,
    );
    expect(screen.getByRole("img", { name: "Logo de Loisirs Club Discovery" })).toBeInTheDocument();
  });

  it("ne code aucune couleur en dur : tout style inline référence une variable CSS des tokens", () => {
    const { container } = render(
      <PlayerTradingCard firstName="Aimé" lastName="Kalonji" positionLabel="Gardien" jerseyNumber={1} motion="static" />,
    );
    const elementsWithStyle = container.querySelectorAll("[style]");
    expect(elementsWithStyle.length).toBeGreaterThan(0);
    for (const el of Array.from(elementsWithStyle)) {
      const styleAttr = el.getAttribute("style") ?? "";
      const hexColors = styleAttr.match(/#[0-9a-fA-F]{3,8}\b/g) ?? [];
      expect(hexColors).toHaveLength(0);
    }
  });

  it("partie B : affiche la note globale à la place du numéro et « n° {n} · {Nom} » dans le bandeau", () => {
    render(
      <PlayerTradingCard
        firstName="Aimé"
        lastName="Kalonji"
        jerseyNumber={4}
        overallRating={78}
        motion="static"
      />,
    );
    expect(screen.getByText("Note globale : 78")).toBeInTheDocument();
    expect(screen.getByText("n° 4 · Aimé Kalonji")).toBeInTheDocument();
    expect(screen.queryByText("Numéro 4")).not.toBeInTheDocument();
  });

  it("partie B : « — » et « pas encore de donnée » quand overallRating est null", () => {
    render(<PlayerTradingCard firstName="Aimé" lastName="Kalonji" overallRating={null} motion="static" />);
    expect(screen.getByText("Note globale : pas encore de donnée")).toBeInTheDocument();
  });

  it("partie B : affiche la grille des six indicateurs quand stats est fourni", () => {
    render(
      <PlayerTradingCard
        firstName="Aimé"
        lastName="Kalonji"
        overallRating={70}
        stats={{
          matchesPlayed: 12,
          goals: 5,
          assists: 3,
          yellowCards: 1,
          redCards: 0,
          attendanceRate: 85,
          averageRating: 7.4,
        }}
        motion="static"
      />,
    );
    expect(screen.queryByText("Statistiques à venir")).not.toBeInTheDocument();
    expect(screen.getByText("Matchs")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("1 jaune, 0 rouge")).toBeInTheDocument();
    expect(screen.getByText("85 %")).toBeInTheDocument();
    expect(screen.getByText("7.4 sur 10")).toBeInTheDocument();
  });

  it("taille « sm » : pas de grille de statistiques, pas de logo ni de poste précis", () => {
    render(
      <PlayerTradingCard
        firstName="Aimé"
        lastName="Kalonji"
        positionDetail="Arrière gauche"
        clubLogoUrl="https://example.test/logo.png"
        clubName="Club"
        size="sm"
        motion="static"
      />,
    );
    expect(screen.queryByText("Statistiques à venir")).not.toBeInTheDocument();
    expect(screen.queryByText("Arrière gauche")).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /^Logo de/ })).not.toBeInTheDocument();
  });

  it("devient un bouton « Voir la fiche détaillée » quand onOpen est fourni", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<PlayerTradingCard firstName="Aimé" lastName="Kalonji" onOpen={onOpen} motion="static" />);
    const button = screen.getByRole("button", { name: "Voir la fiche détaillée de Aimé Kalonji" });
    await user.click(button);
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it.each<[string, ThemeName, ClubBranding | null]>([
    ["Clair", "light", null],
    ["Sombre", "dark", null],
    ["Classic (couleurs du club)", "classic", NAVY_RED_BRANDING],
  ])("s'affiche sans erreur en thème %s", (_label, theme, branding) => {
    renderWithTheme(
      <PlayerTradingCard firstName="Aimé" lastName="Kalonji" positionLabel="Milieu" jerseyNumber={8} motion="static" />,
      theme,
      branding,
    );
    expect(screen.getByText("Aimé Kalonji")).toBeInTheDocument();
  });
});
