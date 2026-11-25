/**
 * Utilitaires communs des graphiques SVG maison (docs/ecrans/
 * club-tableau-de-bord-bureau.md §6). Aucune règle métier : mise à l'échelle,
 * formatage, styles de séries.
 */

import type { CSSProperties } from "react";

export interface NiceScale {
  min: number;
  max: number;
  step: number;
  ticks: number[];
}

function niceStep(rawStep: number): number {
  const exponent = Math.floor(Math.log10(rawStep));
  const base = 10 ** exponent;
  const fraction = rawStep / base;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return nice * base;
}

function roundTo(value: number, step: number): number {
  const decimals = Math.max(0, -Math.floor(Math.log10(step)) + 1);
  return Number(value.toFixed(Math.min(decimals, 10)));
}

/**
 * Échelle « ronde » (pas de 1, 2, 5 x 10^n) englobant [min, max].
 * Gère l'étendue nulle (valeurs toutes égales, toutes à 0) et les grandes valeurs.
 */
export function niceScale(min: number, max: number, targetTicks = 4): NiceScale {
  let lo = Number.isFinite(min) ? min : 0;
  let hi = Number.isFinite(max) ? max : 1;
  if (lo > hi) [lo, hi] = [hi, lo];
  if (lo === hi) {
    if (lo === 0) {
      hi = 1;
    } else if (lo > 0) {
      lo = 0;
    } else {
      hi = 0;
    }
  }
  const step = niceStep((hi - lo) / Math.max(1, targetTicks));
  const scaledMin = roundTo(Math.floor(lo / step) * step, step);
  const scaledMax = roundTo(Math.ceil(hi / step) * step, step);
  const ticks: number[] = [];
  for (let value = scaledMin; value <= scaledMax + step / 2; value += step) {
    ticks.push(roundTo(value, step));
  }
  return { min: scaledMin, max: scaledMax, step, ticks };
}

const NUMBER_FORMAT = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const INTEGER_FORMAT = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
const COMPACT_FORMAT = new Intl.NumberFormat("fr-FR", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/** Valeur écrite sur un graphique (espaces insécables du français). */
export function formatNumber(value: number): string {
  return Math.abs(value) >= 100 ? INTEGER_FORMAT.format(value) : NUMBER_FORMAT.format(value);
}

/** Étiquette d'axe : compacte (« 12 k ») à partir de 10 000. */
export function formatAxisNumber(value: number): string {
  return Math.abs(value) >= 10_000 ? COMPACT_FORMAT.format(value) : formatNumber(value);
}

/** Ajoute l'unité (« % », « $ ») après une espace insécable. */
export function withUnit(text: string, unit?: string): string {
  return unit ? `${text} ${unit}` : text;
}

export function isNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Largeur approximative d'un texte SVG de 12 px (pour réserver les marges). */
export function approxTextWidth(text: string, fontSize = 12): number {
  return Math.ceil(text.length * fontSize * 0.56) + 2;
}

/**
 * Indices d'étiquettes d'axe à afficher : espacées pour ne jamais se
 * chevaucher, ancrées sur la dernière (rotation et troncature interdites).
 */
export function visibleLabelIndexes(count: number, slotWidth: number, labelWidth: number): Set<number> {
  const perLabel = Math.max(1, Math.ceil((labelWidth + 6) / Math.max(1, slotWidth)));
  const shown = new Set<number>();
  for (let index = count - 1; index >= 0; index -= perLabel) shown.add(index);
  return shown;
}

export type SeriesPattern = "solid" | "stripes" | "dots" | "cross";

export interface SeriesStyle {
  /** Variable CSS du thème : jamais une couleur de club. */
  color: string;
  /** Tracé des lignes : plein, tirets, pointillés, tirets-points. */
  dash: string | undefined;
  /** Motif des surfaces (barres, segments) : plein, hachures, points, quadrillage. */
  pattern: SeriesPattern;
}

export const SERIES_STYLES: readonly SeriesStyle[] = [
  { color: "var(--color-series-1)", dash: undefined, pattern: "solid" },
  { color: "var(--color-series-2)", dash: "6 4", pattern: "stripes" },
  { color: "var(--color-series-3)", dash: "2 3", pattern: "dots" },
  { color: "var(--color-series-4)", dash: "8 3 2 3", pattern: "cross" },
];

export function seriesStyle(index: number): SeriesStyle {
  return SERIES_STYLES[index % SERIES_STYLES.length] ?? SERIES_STYLES[0]!;
}

/** Style CSS (HTML) d'une surface à motif : légendes et segments. */
export function patternCss(pattern: SeriesPattern, color: string): CSSProperties {
  const overlay = "var(--color-surface)";
  switch (pattern) {
    case "stripes":
      return {
        backgroundColor: color,
        backgroundImage: `repeating-linear-gradient(45deg, ${overlay} 0 2px, transparent 2px 5px)`,
      };
    case "dots":
      return {
        backgroundColor: color,
        backgroundImage: `radial-gradient(${overlay} 1.2px, transparent 1.5px)`,
        backgroundSize: "5px 5px",
      };
    case "cross":
      return {
        backgroundColor: color,
        backgroundImage: `repeating-linear-gradient(0deg, ${overlay} 0 1px, transparent 1px 5px), repeating-linear-gradient(90deg, ${overlay} 0 1px, transparent 1px 5px)`,
      };
    default:
      return { backgroundColor: color };
  }
}
