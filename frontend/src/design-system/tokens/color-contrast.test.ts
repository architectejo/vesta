import { describe, expect, it } from "vitest";
import {
  contrastRatio,
  darkenUntilContrast,
  deriveAccentOnSurface,
  deriveAccentPair,
  deriveClassicSidebarTokens,
  derivePlayerCardTokens,
  deriveReadableTextColor,
  hexToRgb,
  pickReadableOnColor,
  relativeLuminance,
  rgbToHex,
} from "./color-contrast";
import { LIGHT_SURFACE, LIGHT_SURFACE_MUTED } from "./light-neutrals";

describe("hexToRgb / rgbToHex", () => {
  it("convertit un hexadécimal à 6 chiffres", () => {
    expect(hexToRgb("#1D4ED8")).toEqual({ r: 29, g: 78, b: 216 });
  });

  it("convertit un hexadécimal court à 3 chiffres", () => {
    expect(hexToRgb("#fff")).toEqual({ r: 255, g: 255, b: 255 });
  });

  it("retourne null pour une entrée invalide", () => {
    expect(hexToRgb("pas une couleur")).toBeNull();
  });

  it("fait l'aller-retour hex -> rgb -> hex", () => {
    expect(rgbToHex({ r: 29, g: 78, b: 216 })).toBe("#1d4ed8");
  });
});

describe("relativeLuminance / contrastRatio", () => {
  it("le blanc a une luminance de 1 et le noir de 0", () => {
    expect(relativeLuminance({ r: 255, g: 255, b: 255 })).toBeCloseTo(1, 5);
    expect(relativeLuminance({ r: 0, g: 0, b: 0 })).toBeCloseTo(0, 5);
  });

  it("le contraste blanc/noir est 21:1", () => {
    expect(contrastRatio({ r: 255, g: 255, b: 255 }, { r: 0, g: 0, b: 0 })).toBeCloseTo(21, 1);
  });

  it("le contraste d'une couleur avec elle-même est 1:1", () => {
    const c = { r: 100, g: 120, b: 140 };
    expect(contrastRatio(c, c)).toBeCloseTo(1, 5);
  });
});

describe("pickReadableOnColor", () => {
  it("choisit le texte sombre sur un fond clair (jaune)", () => {
    const yellow = hexToRgb("#FACC15");
    expect(yellow).not.toBeNull();
    const chosen = pickReadableOnColor(yellow!);
    expect(rgbToHex(chosen)).toBe("#111827");
  });

  it("choisit le texte blanc sur un fond sombre", () => {
    const dark = hexToRgb("#111827");
    expect(dark).not.toBeNull();
    const chosen = pickReadableOnColor(dark!);
    expect(rgbToHex(chosen)).toBe("#ffffff");
  });
});

describe("darkenUntilContrast", () => {
  it("assombrit jusqu'à atteindre le contraste cible", () => {
    const light = hexToRgb("#FACC15"); // jaune clair, peu de contraste avec du blanc
    const white = hexToRgb("#FFFFFF");
    expect(light).not.toBeNull();
    expect(white).not.toBeNull();
    const before = contrastRatio(light!, white!);
    expect(before).toBeLessThan(4.5);
    const darkened = darkenUntilContrast(light!, white!, 4.5);
    expect(contrastRatio(darkened, white!)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("deriveAccentPair", () => {
  it("retourne un couple fond/texte lisible pour une couleur de club vive", () => {
    const pair = deriveAccentPair("#FACC15");
    expect(pair).not.toBeNull();
    const bgRgb = hexToRgb(pair!.bg);
    const fgRgb = hexToRgb(pair!.fg);
    expect(bgRgb).not.toBeNull();
    expect(fgRgb).not.toBeNull();
    expect(contrastRatio(bgRgb!, fgRgb!)).toBeGreaterThanOrEqual(4.5);
  });

  it("conserve une couleur de club déjà suffisamment contrastée", () => {
    const pair = deriveAccentPair("#1D4ED8");
    expect(pair).toEqual({ bg: "#1d4ed8", fg: "#ffffff" });
  });

  it("retourne null pour une couleur invalide", () => {
    expect(deriveAccentPair("pas une couleur")).toBeNull();
  });
});

describe("deriveReadableTextColor", () => {
  // Changement (§7.1) : le fond n'a plus de valeur par défaut (le blanc pur n'existe plus
  // dans les neutres) ; les deux premiers tests passent explicitement un blanc de référence.
  it("assombrit une couleur claire pour qu'elle soit lisible en texte sur blanc", () => {
    const result = deriveReadableTextColor("#FACC15", "#FFFFFF");
    expect(result).not.toBeNull();
    const rgb = hexToRgb(result!);
    const white = hexToRgb("#FFFFFF");
    expect(contrastRatio(rgb!, white!)).toBeGreaterThanOrEqual(4.5);
  });

  it("laisse inchangée une couleur déjà lisible", () => {
    expect(deriveReadableTextColor("#1D4ED8", "#FFFFFF")).toBe("#1d4ed8");
  });

  it("garantit le contraste sur le neutre le plus sombre du thème Clair, pas sur du blanc", () => {
    // Bleu lisible sur blanc mais pas sur #E6E9EE : il doit être assombri.
    const raw = "#3A63D0";
    const onWhite = contrastRatio(hexToRgb(raw)!, hexToRgb("#FFFFFF")!);
    const onMuted = contrastRatio(hexToRgb(raw)!, hexToRgb(LIGHT_SURFACE_MUTED)!);
    expect(onWhite).toBeGreaterThanOrEqual(4.5);
    expect(onMuted).toBeLessThan(4.5);
    const result = deriveReadableTextColor(raw, LIGHT_SURFACE_MUTED);
    expect(
      contrastRatio(hexToRgb(result!)!, hexToRgb(LIGHT_SURFACE_MUTED)!),
    ).toBeGreaterThanOrEqual(4.5);
  });

  it("retourne null pour une entrée invalide", () => {
    expect(deriveReadableTextColor("pas une couleur", "#FFFFFF")).toBeNull();
    expect(deriveReadableTextColor("#1D4ED8", "pas une couleur")).toBeNull();
  });
});

describe("deriveAccentOnSurface", () => {
  it("conserve un accent qui atteint 3:1 sur la surface", () => {
    expect(deriveAccentOnSurface("#D2232A", LIGHT_SURFACE)).toBe("#d2232a");
  });

  it("assombrit un accent trop clair pour atteindre 3:1 sur la surface", () => {
    const result = deriveAccentOnSurface("#FACC15", LIGHT_SURFACE);
    expect(result).not.toBe("#facc15");
    expect(contrastRatio(hexToRgb(result!)!, hexToRgb(LIGHT_SURFACE)!)).toBeGreaterThanOrEqual(3);
  });

  it("retourne null pour une entrée invalide", () => {
    expect(deriveAccentOnSurface("nope", LIGHT_SURFACE)).toBeNull();
  });
});

describe("deriveClassicSidebarTokens", () => {
  // Couleur marine purement synthétique (donnée de test, pas une couleur de club codée en dur).
  const NAVY = "#1B2143";

  it("dérive des tokens de barre latérale lisibles pour un fond marine", () => {
    const tokens = deriveClassicSidebarTokens({
      sidebarBg: NAVY,
      sidebarText: "#ffffff",
      primaryText: NAVY,
      surfaceHex: LIGHT_SURFACE,
    });
    expect(tokens).toEqual({
      textMuted: "#bbbcc7", // blanc mélangé à 30 % vers le marine
      hoverBg: "#323756", // marine mélangé à 10 % vers le blanc
      activeBg: LIGHT_SURFACE,
      activeText: "#1b2143",
    });
    const bg = hexToRgb(NAVY)!;
    expect(contrastRatio(hexToRgb(tokens!.textMuted)!, bg)).toBeGreaterThanOrEqual(4.5);
    expect(
      contrastRatio(hexToRgb(tokens!.hoverBg)!, hexToRgb("#ffffff")!),
    ).toBeGreaterThanOrEqual(4.5);
    expect(
      contrastRatio(hexToRgb(tokens!.activeText)!, hexToRgb(tokens!.activeBg)!),
    ).toBeGreaterThanOrEqual(4.5);
  });

  it("garde le texte secondaire à 4,5:1 même quand le mélange à 30 % ne suffit pas", () => {
    // Fond moyen : le mélange à 30 % vers le fond tombe sous 4,5:1, il est réduit par pas de 5 %.
    const mid = "#4F5F80";
    const tokens = deriveClassicSidebarTokens({
      sidebarBg: mid,
      sidebarText: "#ffffff",
      primaryText: mid,
      surfaceHex: LIGHT_SURFACE,
    });
    const bg = hexToRgb(mid)!;
    expect(contrastRatio(hexToRgb("#ffffff")!, bg)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(hexToRgb(tokens!.textMuted)!, bg)).toBeGreaterThanOrEqual(4.5);
    expect(tokens!.textMuted).not.toBe("#ffffff");
  });

  it("retourne null pour une entrée invalide", () => {
    expect(
      deriveClassicSidebarTokens({
        sidebarBg: "nope",
        sidebarText: "#ffffff",
        primaryText: "#000000",
        surfaceHex: LIGHT_SURFACE,
      }),
    ).toBeNull();
  });
});

describe("derivePlayerCardTokens (docs/ecrans/club-carte-joueur.md A6)", () => {
  // Couleurs synthétiques (marine et rouge) : données de test, jamais dans le code.
  const NAVY = "#1B2143";
  const RED_ACCENT = "#d2232a"; // --color-accent déjà dérivé pour ce club (marine/rouge)

  it("club marine et rouge : texte clair, cadre rouge, contrastes respectés", () => {
    const tokens = derivePlayerCardTokens({ primaryHex: NAVY, accentHex: RED_ACCENT });
    expect(tokens).not.toBeNull();
    const from = hexToRgb(tokens!.from)!;
    const to = hexToRgb(tokens!.to)!;
    const fg = hexToRgb(tokens!.fg)!;
    const fgMuted = hexToRgb(tokens!.fgMuted)!;
    const bandBg = hexToRgb(tokens!.bandBg)!;
    const bandFg = hexToRgb(tokens!.bandFg)!;
    const frame = hexToRgb(tokens!.frame)!;

    // Exigence générale (A6.6) : fg >= 4.5:1 sur from et sur to.
    expect(contrastRatio(fg, from)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(fg, to)).toBeGreaterThanOrEqual(4.5);
    // Le nom (band-fg sur band-bg) vise >= 7:1 (A6.3).
    expect(contrastRatio(bandFg, bandBg)).toBeGreaterThanOrEqual(7);
    // fg-muted >= 4.5:1 sur from et sur to (A6.4).
    expect(contrastRatio(fgMuted, from)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(fgMuted, to)).toBeGreaterThanOrEqual(4.5);
    // Le cadre reprend l'accent déjà calculé (rouge du club).
    expect(tokens!.frame).toBe(RED_ACCENT);
    expect(rgbToHex(frame)).toBe(RED_ACCENT);
    // `to` s'éloigne du texte (clair ici) : plus sombre que `from`.
    expect(relativeLuminance(to)).toBeLessThan(relativeLuminance(from));
  });

  it("club jaune (texte foncé) : `to` et `band-bg` s'éclaircissent en s'éloignant du texte foncé", () => {
    const tokens = derivePlayerCardTokens({ primaryHex: "#FACC15", accentHex: "#FACC15" });
    expect(tokens).not.toBeNull();
    const from = hexToRgb(tokens!.from)!;
    const to = hexToRgb(tokens!.to)!;
    const fg = hexToRgb(tokens!.fg)!;
    const bandBg = hexToRgb(tokens!.bandBg)!;
    const bandFg = hexToRgb(tokens!.bandFg)!;

    // Texte foncé attendu sur un jaune vif.
    expect(tokens!.fg).toBe("#111827");
    expect(contrastRatio(fg, from)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(fg, to)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(bandFg, bandBg)).toBeGreaterThanOrEqual(7);
    // Texte foncé : `to` s'éclaircit (s'éloigne du noir) par rapport à `from`.
    expect(relativeLuminance(to)).toBeGreaterThan(relativeLuminance(from));
  });

  it("club sans couleur : retourne null (l'appelant garde les valeurs du thème Clair)", () => {
    expect(derivePlayerCardTokens({ primaryHex: "", accentHex: null })).toBeNull();
    expect(derivePlayerCardTokens({ primaryHex: "pas une couleur", accentHex: null })).toBeNull();
  });

  it("sans accent fourni, replie le cadre sur `from`", () => {
    const tokens = derivePlayerCardTokens({ primaryHex: NAVY, accentHex: null });
    expect(tokens).not.toBeNull();
    expect(tokens!.frame).toBe(tokens!.from);
  });
});
