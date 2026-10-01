import { describe, expect, it } from "vitest";
import { contrastRatio, hexToRgb } from "../../design-system/tokens/color-contrast";
import { pickColorsFromPixels } from "./colorFromImage";

type Rgba = [number, number, number, number];

// Couleurs purement synthétiques : un marine et un rouge de test, sans lien avec un club réel.
const WHITE: Rgba = [255, 255, 255, 255];
const BLACK: Rgba = [0, 0, 0, 255];
const NAVY: Rgba = [27, 33, 67, 255];
const RED: Rgba = [210, 35, 42, 255];
const SKY: Rgba = [47, 111, 181, 255];
const GREY: Rgba = [128, 128, 128, 255];
const TRANSPARENT_RED: Rgba = [210, 35, 42, 0];

/** Construit un tableau RGBA (format `ImageData.data`) à partir de (couleur, nombre de pixels). */
function pixels(...parts: Array<[Rgba, number]>): Uint8ClampedArray {
  const values: number[] = [];
  for (const [color, count] of parts) {
    for (let i = 0; i < count; i += 1) values.push(...color);
  }
  return Uint8ClampedArray.from(values);
}

/** Écart maximal par canal entre deux couleurs hexadécimales. */
function channelDistance(a: string, b: string): number {
  const ra = hexToRgb(a)!;
  const rb = hexToRgb(b)!;
  return Math.max(Math.abs(ra.r - rb.r), Math.abs(ra.g - rb.g), Math.abs(ra.b - rb.b));
}

describe("pickColorsFromPixels", () => {
  it("image moitié blanche, marine et rouge : marine en principale, rouge en secondaire", () => {
    const result = pickColorsFromPixels(pixels([WHITE, 500], [NAVY, 400], [RED, 100]));
    expect(result).not.toBeNull();
    expect(channelDistance(result!.primary, "#1b2143")).toBeLessThanOrEqual(2);
    expect(channelDistance(result!.secondary, "#d2232a")).toBeLessThanOrEqual(2);
  });

  it("ne renvoie jamais le gris moyen produit par une moyenne de tous les pixels", () => {
    const result = pickColorsFromPixels(pixels([WHITE, 500], [NAVY, 400], [RED, 100]));
    expect(result!.primary).not.toBe(result!.secondary);
    // La principale est foncée : elle ne peut pas être un mélange dominé par le blanc.
    expect(contrastRatio(hexToRgb(result!.primary)!, hexToRgb("#ffffff")!)).toBeGreaterThan(10);
  });

  it("le fond blanc majoritaire n'influence pas le choix", () => {
    const result = pickColorsFromPixels(pixels([WHITE, 3000], [NAVY, 60], [RED, 40]));
    expect(channelDistance(result!.primary, "#1b2143")).toBeLessThanOrEqual(2);
    expect(channelDistance(result!.secondary, "#d2232a")).toBeLessThanOrEqual(2);
  });

  it("choisit comme secondaire la teinte la plus éloignée, pas la plus proche", () => {
    // Le bleu du ballon est proche du marine (teinte) et le rouge est à l'opposé.
    const result = pickColorsFromPixels(pixels([NAVY, 400], [SKY, 100], [RED, 100]));
    expect(channelDistance(result!.secondary, "#d2232a")).toBeLessThanOrEqual(2);
  });

  it("ignore une teinte secondaire sous 3 % des pixels retenus", () => {
    const result = pickColorsFromPixels(pixels([NAVY, 980], [RED, 20]));
    expect(result!.secondary).toBe(result!.primary);
  });

  it("une seule teinte : la secondaire est égale à la principale", () => {
    const result = pickColorsFromPixels(pixels([WHITE, 100], [NAVY, 100]));
    expect(result).not.toBeNull();
    expect(result!.secondary).toBe(result!.primary);
  });

  it("logo noir et blanc : aucune proposition (null)", () => {
    expect(pickColorsFromPixels(pixels([WHITE, 500], [BLACK, 500]))).toBeNull();
  });

  it("logo en gris (peu saturé) : aucune proposition (null)", () => {
    expect(pickColorsFromPixels(pixels([WHITE, 500], [GREY, 500]))).toBeNull();
  });

  it("moins de 2 % de pixels retenus : aucune proposition (null)", () => {
    expect(pickColorsFromPixels(pixels([WHITE, 990], [NAVY, 10]))).toBeNull();
  });

  it("ignore les pixels transparents, quelle que soit leur couleur", () => {
    const result = pickColorsFromPixels(pixels([TRANSPARENT_RED, 900], [NAVY, 100]));
    expect(channelDistance(result!.primary, "#1b2143")).toBeLessThanOrEqual(2);
    expect(result!.secondary).toBe(result!.primary);
  });

  it("image entièrement transparente : null", () => {
    expect(pickColorsFromPixels(pixels([TRANSPARENT_RED, 500]))).toBeNull();
  });

  it("image vide : null", () => {
    expect(pickColorsFromPixels(new Uint8ClampedArray(0))).toBeNull();
  });

  it("est déterministe : deux appels identiques donnent le même résultat", () => {
    const data = pixels([NAVY, 300], [RED, 300], [SKY, 300]);
    expect(pickColorsFromPixels(data)).toEqual(pickColorsFromPixels(data));
  });
});
