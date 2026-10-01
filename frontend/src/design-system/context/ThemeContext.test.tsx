import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ClubBrandingProvider, type ClubBranding } from "./ClubBrandingContext";
import { ThemeProvider, useTheme, type ThemeName } from "./ThemeContext";
import { contrastRatio, hexToRgb } from "../tokens/color-contrast";
import { LIGHT_SURFACE, LIGHT_SURFACE_MUTED } from "../tokens/light-neutrals";

const FICTITIOUS_BRANDING: ClubBranding = {
  name: "Club de démonstration",
  logoUrl: null,
  primaryColor: "#FACC15", // jaune vif fictif, peu contrasté avec du blanc
  secondaryColor: "#111827",
};

// Couleurs synthétiques (marine et rouge) : donnée de test uniquement, jamais dans le code.
const NAVY_RED_BRANDING: ClubBranding = {
  name: "Club de démonstration",
  logoUrl: null,
  primaryColor: "#1B2143",
  secondaryColor: "#D2232A",
};

const SIDEBAR_TOKENS = [
  "--color-sidebar-text-muted",
  "--color-sidebar-hover-bg",
  "--color-sidebar-active-bg",
  "--color-sidebar-active-text",
] as const;

function ThemeConsumer() {
  const { theme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="current-theme">{theme}</span>
      <button type="button" onClick={() => setTheme("dark")}>
        Sombre
      </button>
      <button type="button" onClick={() => setTheme("classic")}>
        Classic
      </button>
    </div>
  );
}

function renderWithProviders(branding: ClubBranding | null, initialTheme?: ThemeName) {
  const tree = (
    <ThemeProvider initialTheme={initialTheme}>
      <ThemeConsumer />
    </ThemeProvider>
  );
  return render(
    branding ? <ClubBrandingProvider branding={branding}>{tree}</ClubBrandingProvider> : tree,
  );
}

describe("ThemeProvider / useTheme", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.removeAttribute("style");
  });

  afterEach(() => {
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.removeAttribute("style");
  });

  it("pose data-theme sur <html> et mémorise le choix en localStorage", async () => {
    const user = userEvent.setup();
    renderWithProviders(null, "light");

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");

    await user.click(screen.getByRole("button", { name: "Sombre" }));

    expect(screen.getByTestId("current-theme")).toHaveTextContent("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem("vesta:theme")).toBe("dark");
  });

  it("applique des couleurs d'accent lisibles en thème Classic à partir des couleurs du club", async () => {
    const user = userEvent.setup();
    renderWithProviders(FICTITIOUS_BRANDING, "light");

    await user.click(screen.getByRole("button", { name: "Classic" }));

    const sidebarBg = document.documentElement.style.getPropertyValue("--color-sidebar-bg");
    const sidebarText = document.documentElement.style.getPropertyValue("--color-sidebar-text");
    expect(sidebarBg).not.toBe("");
    expect(sidebarText).not.toBe("");

    const bgRgb = hexToRgb(sidebarBg);
    const textRgb = hexToRgb(sidebarText);
    expect(bgRgb).not.toBeNull();
    expect(textRgb).not.toBeNull();
    // La propriété qui compte réellement (2.4) : le couple posé est lisible,
    // quelle que soit la couleur de club fournie.
    expect(contrastRatio(bgRgb!, textRgb!)).toBeGreaterThanOrEqual(4.5);
  });

  it("retire les couleurs d'accent quand on quitte le thème Classic", async () => {
    const user = userEvent.setup();
    renderWithProviders(FICTITIOUS_BRANDING, "classic");

    expect(
      document.documentElement.style.getPropertyValue("--color-sidebar-bg"),
    ).not.toBe("");

    await user.click(screen.getByRole("button", { name: "Sombre" }));

    expect(document.documentElement.style.getPropertyValue("--color-sidebar-bg")).toBe("");
  });

  it("retire aussi les quatre tokens de barre latérale en quittant Classic", async () => {
    const user = userEvent.setup();
    renderWithProviders(NAVY_RED_BRANDING, "classic");
    const style = document.documentElement.style;
    for (const token of SIDEBAR_TOKENS) expect(style.getPropertyValue(token)).not.toBe("");

    await user.click(screen.getByRole("button", { name: "Sombre" }));

    for (const token of SIDEBAR_TOKENS) expect(style.getPropertyValue(token)).toBe("");
  });

  it("dérive les tokens de barre latérale Classic de la couleur primaire du club", () => {
    renderWithProviders(NAVY_RED_BRANDING, "classic");
    const style = document.documentElement.style;

    expect(style.getPropertyValue("--color-sidebar-bg")).toBe("#1b2143");
    expect(style.getPropertyValue("--color-sidebar-text")).toBe("#ffffff");
    // Valeurs calculées par formule (§7.2), pas écrites en dur dans le code.
    expect(style.getPropertyValue("--color-sidebar-text-muted")).toBe("#bbbcc7");
    expect(style.getPropertyValue("--color-sidebar-hover-bg")).toBe("#323756");
    expect(style.getPropertyValue("--color-sidebar-active-bg")).toBe(LIGHT_SURFACE);
    expect(style.getPropertyValue("--color-sidebar-active-text")).toBe("#1b2143");
    expect(style.getPropertyValue("--color-accent")).toBe("#d2232a");
  });

  it("garantit la lisibilité de la barre latérale Classic avec un primaire marine", () => {
    renderWithProviders(NAVY_RED_BRANDING, "classic");
    const value = (token: string) => hexToRgb(document.documentElement.style.getPropertyValue(token))!;

    const bg = value("--color-sidebar-bg");
    expect(contrastRatio(value("--color-sidebar-text"), bg)).toBeGreaterThanOrEqual(7);
    expect(contrastRatio(value("--color-sidebar-text-muted"), bg)).toBeGreaterThanOrEqual(4.5);
    const hover = value("--color-sidebar-hover-bg");
    expect(contrastRatio(value("--color-sidebar-text"), hover)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(value("--color-sidebar-text-muted"), hover)).toBeGreaterThanOrEqual(4.5);
    const active = value("--color-sidebar-active-bg");
    expect(contrastRatio(value("--color-sidebar-active-text"), active)).toBeGreaterThanOrEqual(7);
    // Liseré d'accent posé sur la pastille active : composant graphique, 3:1 minimum.
    expect(contrastRatio(value("--color-accent"), active)).toBeGreaterThanOrEqual(3);
  });

  it("calcule le texte de lien contre le neutre le plus sombre (pas contre du blanc)", () => {
    renderWithProviders(NAVY_RED_BRANDING, "classic");
    const primaryText = hexToRgb(
      document.documentElement.style.getPropertyValue("--color-primary-text"),
    )!;
    expect(contrastRatio(primaryText, hexToRgb(LIGHT_SURFACE_MUTED)!)).toBeGreaterThanOrEqual(4.5);
  });

  it("assombrit un accent trop clair pour garder 3:1 sur la carte", () => {
    renderWithProviders({ ...NAVY_RED_BRANDING, secondaryColor: "#FACC15" }, "classic");
    const accent = hexToRgb(document.documentElement.style.getPropertyValue("--color-accent"))!;
    expect(contrastRatio(accent, hexToRgb(LIGHT_SURFACE)!)).toBeGreaterThanOrEqual(3);
  });

  it("sans couleurs de club, Classic ne pose aucun jeton et reste sur les neutres du Clair", () => {
    renderWithProviders({ ...NAVY_RED_BRANDING, primaryColor: null, secondaryColor: null }, "classic");
    expect(document.documentElement.getAttribute("style") ?? "").toBe("");
  });

  it("ne change pas les accents en dehors du thème Classic même avec des couleurs de club", () => {
    renderWithProviders(FICTITIOUS_BRANDING, "dark");
    expect(document.documentElement.style.getPropertyValue("--color-primary")).toBe("");
  });

  it("dérive les huit tokens de carte de joueur pour un club marine et rouge (club-carte-joueur.md A6)", () => {
    renderWithProviders(NAVY_RED_BRANDING, "classic");
    const value = (token: string) => document.documentElement.style.getPropertyValue(token);
    const rgb = (token: string) => hexToRgb(value(token))!;

    for (const token of [
      "--color-player-card-from",
      "--color-player-card-to",
      "--color-player-card-fg",
      "--color-player-card-fg-muted",
      "--color-player-card-band-bg",
      "--color-player-card-band-fg",
      "--color-player-card-frame",
      "--color-player-card-frame-highlight",
    ]) {
      expect(value(token)).not.toBe("");
    }

    expect(contrastRatio(rgb("--color-player-card-fg"), rgb("--color-player-card-from"))).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(rgb("--color-player-card-fg"), rgb("--color-player-card-to"))).toBeGreaterThanOrEqual(4.5);
    expect(
      contrastRatio(rgb("--color-player-card-band-fg"), rgb("--color-player-card-band-bg")),
    ).toBeGreaterThanOrEqual(7);
    // Le cadre reprend l'accent (rouge du club) déjà posé par le thème.
    expect(value("--color-player-card-frame")).toBe(value("--color-accent"));
  });

  it("dérive des tokens de carte de joueur lisibles pour un club jaune (texte foncé)", () => {
    renderWithProviders({ ...FICTITIOUS_BRANDING, primaryColor: "#FACC15" }, "classic");
    const rgb = (token: string) => hexToRgb(document.documentElement.style.getPropertyValue(token))!;

    expect(
      contrastRatio(rgb("--color-player-card-fg"), rgb("--color-player-card-from")),
    ).toBeGreaterThanOrEqual(4.5);
    expect(
      contrastRatio(rgb("--color-player-card-fg"), rgb("--color-player-card-to")),
    ).toBeGreaterThanOrEqual(4.5);
    expect(
      contrastRatio(rgb("--color-player-card-band-fg"), rgb("--color-player-card-band-bg")),
    ).toBeGreaterThanOrEqual(7);
  });

  it("club sans couleur : Classic ne pose aucun token de carte de joueur (valeurs du Clair conservées)", () => {
    renderWithProviders({ ...NAVY_RED_BRANDING, primaryColor: null, secondaryColor: null }, "classic");
    expect(
      document.documentElement.style.getPropertyValue("--color-player-card-from"),
    ).toBe("");
  });

  it("retire les tokens de carte de joueur en quittant Classic", async () => {
    const user = userEvent.setup();
    renderWithProviders(NAVY_RED_BRANDING, "classic");
    expect(
      document.documentElement.style.getPropertyValue("--color-player-card-from"),
    ).not.toBe("");

    await user.click(screen.getByRole("button", { name: "Sombre" }));

    expect(document.documentElement.style.getPropertyValue("--color-player-card-from")).toBe("");
  });

  it("lève une erreur explicite si useTheme est utilisé hors ThemeProvider", () => {
    function Broken() {
      useTheme();
      return null;
    }
    expect(() => {
      act(() => {
        render(<Broken />);
      });
    }).toThrow(/ThemeProvider/);
  });
});
