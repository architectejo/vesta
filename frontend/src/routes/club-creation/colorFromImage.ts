/**
 * Extraction de deux couleurs à partir d'un logo, entièrement dans le
 * navigateur (clubs-creation.md §4.1, CDC 6.7 : « rien n'est envoyé avant la
 * fin »), conforme au principe du 2.4 de docs/lot0/design-system.md et à la
 * révision du 28/09/2026 (§7.2) :
 *
 * 1. l'image est réduite à 64 × 64 px ;
 * 2. on écarte les pixels transparents (alpha < 128), quasi blancs
 *    (luminosité HSL > 0,90), quasi noirs (< 0,08) et peu saturés (< 0,25) :
 *    le fond blanc et les gris d'anticrénelage ne comptent donc pas ;
 * 3. les pixels restants sont classés dans un histogramme de 24 teintes
 *    (15° chacune) × 3 niveaux de luminosité ; la couleur d'une case est la
 *    moyenne RVB de ses pixels (absorbe le bruit JPEG) ;
 * 4. principale = case la plus peuplée ;
 * 5. secondaire = parmi les cases pesant au moins 3 % des pixels retenus, celle
 *    dont la teinte est la plus éloignée de la principale sur le cercle ;
 * 6. moins de 2 % de pixels retenus (logo noir et blanc) : `null`, pas de
 *    proposition. Une seule teinte : secondaire = principale.
 *
 * Le résultat n'est qu'une proposition : le Président garde la main pour
 * ajuster les couleurs avant d'enregistrer.
 */

export interface ExtractedColors {
  primary: string;
  secondary: string;
}

const SAMPLE_SIZE = 64;
const MIN_ALPHA = 128;
const MAX_LIGHTNESS = 0.9;
const MIN_LIGHTNESS = 0.08;
const MIN_SATURATION = 0.25;
const HUE_BINS = 24;
const HUE_BIN_WIDTH = 360 / HUE_BINS;
const LIGHTNESS_LEVELS = 3;
/** Part minimale de pixels retenus pour qu'une case puisse être la couleur secondaire. */
const MIN_SECONDARY_SHARE = 0.03;
/** Part minimale de pixels retenus (sur les pixels opaques) pour proposer quoi que ce soit. */
const MIN_RETAINED_SHARE = 0.02;
/** Écart de teinte sous lequel deux cases sont considérées comme la même teinte. */
const MIN_HUE_GAP = 30;

interface Bin {
  count: number;
  r: number;
  g: number;
  b: number;
}

function toHex(value: number): string {
  return Math.max(0, Math.min(255, Math.round(value)))
    .toString(16)
    .padStart(2, "0");
}

/** Teinte (0–360), saturation et luminosité (0–1) HSL d'une couleur RVB (0–255). */
function rgbToHsl(r: number, g: number, b: number): { h: number; s: number; l: number } {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const delta = max - min;
  const l = (max + min) / 2;
  if (delta === 0) return { h: 0, s: 0, l };

  const s = delta / (1 - Math.abs(2 * l - 1));
  let h: number;
  if (max === rn) h = ((gn - bn) / delta) % 6;
  else if (max === gn) h = (bn - rn) / delta + 2;
  else h = (rn - gn) / delta + 4;
  h *= 60;
  if (h < 0) h += 360;
  return { h, s, l };
}

function hueDistance(a: number, b: number): number {
  const diff = Math.abs(a - b) % 360;
  return diff > 180 ? 360 - diff : diff;
}

/**
 * Choisit les couleurs principale et secondaire dans un tableau de pixels RGBA
 * (format de `ImageData.data`). Fonction pure, testable sans canvas.
 * Retourne `null` quand aucune couleur de marque ne peut être proposée
 * (image vide, entièrement transparente, noir et blanc ou grise).
 */
export function pickColorsFromPixels(data: ArrayLike<number>): ExtractedColors | null {
  const bins = new Map<number, Bin>();
  let opaque = 0;
  let retained = 0;

  for (let i = 0; i + 3 < data.length; i += 4) {
    const alpha = data[i + 3] ?? 0;
    if (alpha < MIN_ALPHA) continue;
    opaque += 1;

    const r = data[i] ?? 0;
    const g = data[i + 1] ?? 0;
    const b = data[i + 2] ?? 0;
    const { h, s, l } = rgbToHsl(r, g, b);
    if (l > MAX_LIGHTNESS || l < MIN_LIGHTNESS || s < MIN_SATURATION) continue;

    const hueBin = Math.floor(h / HUE_BIN_WIDTH) % HUE_BINS;
    const lightnessBin = Math.min(LIGHTNESS_LEVELS - 1, Math.floor(l * LIGHTNESS_LEVELS));
    const key = hueBin * LIGHTNESS_LEVELS + lightnessBin;
    const bin = bins.get(key) ?? { count: 0, r: 0, g: 0, b: 0 };
    bin.count += 1;
    bin.r += r;
    bin.g += g;
    bin.b += b;
    bins.set(key, bin);
    retained += 1;
  }

  if (opaque === 0 || retained === 0 || retained / opaque < MIN_RETAINED_SHARE) return null;

  // Cases triées par clé : à égalité de population, le résultat reste déterministe.
  const entries = [...bins.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, bin]) => {
      const r = bin.r / bin.count;
      const g = bin.g / bin.count;
      const b = bin.b / bin.count;
      return { count: bin.count, r, g, b, hue: rgbToHsl(r, g, b).h };
    });

  let primary = entries[0];
  if (!primary) return null;
  for (const entry of entries) {
    if (entry.count > primary.count) primary = entry;
  }

  let secondary = primary;
  let secondaryGap = 0;
  for (const entry of entries) {
    if (entry.count / retained < MIN_SECONDARY_SHARE) continue;
    const gap = hueDistance(entry.hue, primary.hue);
    if (gap < MIN_HUE_GAP) continue;
    if (gap > secondaryGap || (gap === secondaryGap && entry.count > secondary.count)) {
      secondary = entry;
      secondaryGap = gap;
    }
  }

  const toColor = (c: { r: number; g: number; b: number }): string =>
    `#${toHex(c.r)}${toHex(c.g)}${toHex(c.b)}`;
  return { primary: toColor(primary), secondary: toColor(secondary) };
}

export async function extractColorsFromImage(file: File): Promise<ExtractedColors | null> {
  if (typeof document === "undefined") return null;

  const objectUrl = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("image-load-failed"));
      img.src = objectUrl;
    });

    const canvas = document.createElement("canvas");
    canvas.width = SAMPLE_SIZE;
    canvas.height = SAMPLE_SIZE;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;
    ctx.drawImage(image, 0, 0, SAMPLE_SIZE, SAMPLE_SIZE);
    const { data } = ctx.getImageData(0, 0, SAMPLE_SIZE, SAMPLE_SIZE);
    return pickColorsFromPixels(data);
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
