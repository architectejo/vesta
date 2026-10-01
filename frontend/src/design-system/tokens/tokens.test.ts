import { describe, expect, it } from "vitest";
import tokensCss from "./tokens.css?raw";
import { contrastRatio, hexToRgb } from "./color-contrast";
import { LIGHT_SURFACE, LIGHT_SURFACE_MUTED } from "./light-neutrals";

/** Sépare le bloc `@theme` (Clair / Classic par défaut) du bloc `[data-theme="dark"]`. */
const DARK_MARKER = '[data-theme="dark"]';
const CLASSIC_MARKER = "Thème Classic (2.4)";
const darkStart = tokensCss.indexOf(DARK_MARKER);
const lightBlock = tokensCss.slice(0, darkStart);
const darkBlock = tokensCss.slice(darkStart, tokensCss.indexOf(CLASSIC_MARKER));

function tokenIn(block: string, name: string): string {
  const match = new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})\\s*;`).exec(block);
  if (!match?.[1]) throw new Error(`Token ${name} introuvable`);
  return match[1].toLowerCase();
}

const light = (name: string): string => tokenIn(lightBlock, name);
const dark = (name: string): string => tokenIn(darkBlock, name);

function ratio(a: string, b: string): number {
  return contrastRatio(hexToRgb(a)!, hexToRgb(b)!);
}

describe("tokens.css : thème Clair adouci (§7.1)", () => {
  it("n'utilise plus de blanc pur pour les grandes surfaces", () => {
    for (const name of [
      "--color-bg",
      "--color-surface",
      "--color-surface-muted",
      "--color-sidebar-bg",
    ]) {
      expect(light(name)).not.toBe("#ffffff");
    }
  });

  it("garde les neutres synchronisés avec light-neutrals.ts", () => {
    expect(light("--color-surface")).toBe(LIGHT_SURFACE);
    expect(light("--color-surface-muted")).toBe(LIGHT_SURFACE_MUTED);
    expect(light("--color-sidebar-bg")).toBe(LIGHT_SURFACE);
    expect(light("--color-sidebar-active-bg")).toBe(LIGHT_SURFACE_MUTED);
  });

  it("conserve la hiérarchie fond de page < carte", () => {
    expect(ratio(light("--color-surface"), light("--color-bg"))).toBeGreaterThan(1.1);
  });

  it("texte principal sur carte, fond et en-tête de tableau : au moins 7:1", () => {
    const text = light("--color-text");
    expect(ratio(text, light("--color-surface"))).toBeGreaterThanOrEqual(7);
    expect(ratio(text, light("--color-bg"))).toBeGreaterThanOrEqual(7);
    expect(ratio(text, light("--color-surface-muted"))).toBeGreaterThanOrEqual(7);
  });

  it("texte secondaire sur carte, fond et en-tête de tableau : au moins 4,5:1", () => {
    const muted = light("--color-text-muted");
    expect(ratio(muted, light("--color-surface"))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(muted, light("--color-bg"))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(muted, light("--color-surface-muted"))).toBeGreaterThanOrEqual(4.5);
  });

  it("bordure de champ sur tous les fonds neutres : au moins 3:1", () => {
    const border = light("--color-border-strong");
    expect(ratio(border, light("--color-surface"))).toBeGreaterThanOrEqual(3);
    expect(ratio(border, light("--color-bg"))).toBeGreaterThanOrEqual(3);
    expect(ratio(border, light("--color-surface-muted"))).toBeGreaterThanOrEqual(3);
  });

  it("lien et bouton principal du Clair restent lisibles sur les nouveaux neutres", () => {
    const primaryText = light("--color-primary-text");
    expect(ratio(primaryText, light("--color-surface"))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(primaryText, light("--color-bg"))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(primaryText, light("--color-surface-muted"))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(light("--color-on-primary"), light("--color-primary"))).toBeGreaterThanOrEqual(
      4.5,
    );
  });

  it("anneau de focus visible sur le fond de page : au moins 3:1", () => {
    expect(ratio(light("--color-focus"), light("--color-bg"))).toBeGreaterThanOrEqual(3);
  });

  it("badge gris lisible (7:1) et distinct de la carte", () => {
    const badgeBg = light("--color-status-neutral-bg");
    expect(ratio(light("--color-status-neutral-fg"), badgeBg)).toBeGreaterThanOrEqual(7);
    expect(ratio(badgeBg, light("--color-surface"))).toBeGreaterThan(1.05);
  });

  it("les séparateurs et squelettes restent distincts de la carte", () => {
    expect(ratio(light("--color-border"), light("--color-surface"))).toBeGreaterThan(1.2);
    expect(ratio(light("--color-skeleton"), light("--color-surface"))).toBeGreaterThan(1.2);
  });

  it("texte de barre latérale (Clair) : 7:1 principal, 4,5:1 secondaire et survol", () => {
    const bg = light("--color-sidebar-bg");
    expect(ratio(light("--color-sidebar-text"), bg)).toBeGreaterThanOrEqual(7);
    expect(ratio(light("--color-sidebar-text-muted"), bg)).toBeGreaterThanOrEqual(4.5);
    const hover = light("--color-sidebar-hover-bg");
    expect(ratio(light("--color-sidebar-text"), hover)).toBeGreaterThanOrEqual(4.5);
    expect(ratio(light("--color-sidebar-text-muted"), hover)).toBeGreaterThanOrEqual(4.5);
    expect(
      ratio(light("--color-sidebar-active-text"), light("--color-sidebar-active-bg")),
    ).toBeGreaterThanOrEqual(7);
  });
});

describe("tokens.css : thème Sombre (barre latérale)", () => {
  it("définit les quatre tokens de barre latérale, lisibles sur le fond sombre", () => {
    const bg = dark("--color-sidebar-bg");
    expect(ratio(dark("--color-sidebar-text-muted"), bg)).toBeGreaterThanOrEqual(4.5);
    const hover = dark("--color-sidebar-hover-bg");
    expect(ratio(dark("--color-sidebar-text"), hover)).toBeGreaterThanOrEqual(4.5);
    expect(ratio(dark("--color-sidebar-text-muted"), hover)).toBeGreaterThanOrEqual(4.5);
    expect(
      ratio(dark("--color-sidebar-active-text"), dark("--color-sidebar-active-bg")),
    ).toBeGreaterThanOrEqual(7);
  });
});

describe("tokens.css : marque blanche (règle 18)", () => {
  it("ne contient aucune couleur de club, seulement des neutres et des couleurs de statut", () => {
    // Couleurs du logo du club pilote : ne doivent jamais apparaître dans les tokens de la plateforme.
    const lowered = tokensCss.toLowerCase();
    expect(lowered).not.toContain("#1b2143");
    expect(lowered).not.toContain("#d2232a");
  });
});
