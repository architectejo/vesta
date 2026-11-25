/**
 * Mise en forme et lecture des saisies des tests de performance.
 *
 * Aucune règle métier : la vitesse « officielle », le classement et les
 * progressions sont calculés par l'API. Ici, seulement :
 * - l'affichage du chrono et un aperçu de vitesse INDICATIF ;
 * - la lecture de saisies décimales françaises SANS flottant (le temps part
 *   au serveur en millisecondes entières, les distances et valeurs en chaînes).
 */

import type { PerformanceTest } from "../../../api/performance";
import type { ItemFields } from "./measureTypes";

const NBSP = " ";

function pad(value: number, size = 2): string {
  return String(value).padStart(size, "0");
}

/** Chrono en cours : « 00:04,37 » (centièmes tronqués, jamais arrondis vers le haut). */
export function formatStopwatch(ms: number): string {
  const centis = Math.floor(Math.max(0, ms) / 10);
  const minutes = Math.floor(centis / 6000);
  const seconds = Math.floor((centis % 6000) / 100);
  return `${pad(minutes)}:${pad(seconds)},${pad(centis % 100)}`;
}

/** Temps figé : « 4,52 s » ; au-delà d'une minute « 1 min 05,30 s » (même règle que l'API). */
export function formatTimeMs(ms: number): string {
  const centis = Math.floor((ms + 5) / 10);
  if (centis >= 6000) {
    const minutes = Math.floor(centis / 6000);
    const rest = centis % 6000;
    return `${minutes} min ${pad(Math.floor(rest / 100))},${pad(rest % 100)} s`;
  }
  return `${Math.floor(centis / 100)},${pad(centis % 100)} s`;
}

/**
 * Aperçu de vitesse affiché pendant la saisie, À TITRE INDICATIF seulement :
 * distance ÷ temps, en km/h. La valeur officielle est recalculée par l'API.
 */
export function indicativeSpeedKmh(distanceM: string | null, timeMs: number): string | null {
  if (distanceM === null || timeMs <= 0) return null;
  const distance = Number(distanceM);
  if (!Number.isFinite(distance) || distance <= 0) return null;
  const kmh = (distance * 3600) / timeMs;
  return `${kmh.toFixed(1).replace(".", ",")}${NBSP}km/h`;
}

const SECONDS_RE = /^(\d{1,5})(?:[.,](\d{1,3}))?$/;
const MIN_SEC_RE = /^(\d{1,3}):(\d{1,2})(?:[.,](\d{1,3}))?$/;

/**
 * « 4,52 » -> 4520 ; « 1:05,30 » -> 65300. Calcul entier (aucun flottant).
 * `null` si la saisie n'est pas un temps valide ou vaut 0.
 */
export function parseTimeToMs(text: string): number | null {
  const clean = text.trim();
  const simple = SECONDS_RE.exec(clean);
  let ms: number;
  if (simple) {
    ms = Number(simple[1]) * 1000 + Number((simple[2] ?? "").padEnd(3, "0"));
  } else {
    const composed = MIN_SEC_RE.exec(clean);
    if (!composed) return null;
    const seconds = Number(composed[2]);
    if (seconds > 59) return null;
    ms = Number(composed[1]) * 60_000 + seconds * 1000 + Number((composed[3] ?? "").padEnd(3, "0"));
  }
  return ms > 0 ? ms : null;
}

/** « 2 650,5 » ou « 2650,5 » -> « 2650.5 » (chaîne décimale pour l'API). `null` si invalide. */
export function parseDecimalString(text: string, maxDecimals = 2): string | null {
  const clean = text.trim().replace(/[\s  ]/g, "").replace(",", ".");
  const match = /^(\d{1,7})(?:\.(\d+))?$/.exec(clean);
  if (!match) return null;
  const decimals = match[2] ?? "";
  if (decimals.length > maxDecimals) return null;
  return decimals ? `${match[1]}.${decimals}` : (match[1] ?? null);
}

export function parseCount(text: string): number | null {
  const clean = text.trim();
  return /^\d{1,6}$/.test(clean) ? Number(clean) : null;
}

/** Centièmes entiers d'une chaîne décimale (≤ 2 décimales), sans flottant. */
export function toHundredths(decimal: string): number {
  const [whole = "0", frac = ""] = decimal.split(".");
  return Number(whole) * 100 + Number(frac.padEnd(2, "0").slice(0, 2));
}

export function fromHundredths(hundredths: number): string {
  const whole = Math.floor(hundredths / 100);
  const frac = hundredths % 100;
  return frac === 0 ? String(whole) : `${whole}.${pad(frac)}`.replace(/0$/, "");
}

/** Secondes -> « 12 min » / « 1 min 30 s » / « 45 s ». */
export function formatDurationS(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds} s`;
  return seconds === 0 ? `${minutes} min` : `${minutes} min ${pad(seconds)} s`;
}

export function formatLocalDate(isoDate: string): string {
  return new Date(`${isoDate.slice(0, 10)}T12:00:00`).toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function formatLocalDateTime(iso: string): string {
  const date = new Date(iso);
  return `${date.toLocaleDateString("fr-FR", { day: "numeric", month: "long" })} à ${date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

/** Valeur brute d'un résultat pour un graphique (affichage seulement). */
export function chartValue(
  kind: string,
  value: { time_ms: number | null; distance_m: string | null; count: number | null; value: string | null },
): number | null {
  if (kind === "timed_distance") return value.time_ms === null ? null : value.time_ms / 1000;
  if (kind === "distance_in_time") return value.distance_m === null ? null : Number(value.distance_m);
  if (kind === "repetitions") return value.count;
  return value.value === null ? null : Number(value.value);
}

export const KIND_OPTIONS = [
  { value: "timed_distance", label: "Chrono sur distance" },
  { value: "distance_in_time", label: "Distance en temps donné" },
  { value: "repetitions", label: "Nombre de répétitions" },
  { value: "free", label: "Saisie libre" },
] as const;

/** Liste fermée des unités (CDC partie C2) : jamais de texte libre, aucune unité de santé. */
export const UNIT_OPTIONS = [
  { value: "seconds", label: "secondes" },
  { value: "meters", label: "mètres" },
  { value: "kmh", label: "km/h" },
  { value: "repetitions", label: "répétitions" },
  { value: "points", label: "points" },
  { value: "percent", label: "pourcentage" },
] as const;

/** Texte lisible d'une mesure en attente (récapitulatif) : simple mise en forme locale, jamais un calcul officiel. */
export function describeFields(test: Pick<PerformanceTest, "attempts" | "unit_label">, fields: ItemFields): string {
  if (fields.outcome === "dnf") return "Abandon";
  if (fields.time_ms !== undefined) return formatTimeMs(fields.time_ms);
  if (fields.distance_m !== undefined) return `${fields.distance_m.replace(".", ",")}${NBSP}m`;
  if (fields.count !== undefined) return test.attempts ? `${fields.count} sur ${test.attempts}` : String(fields.count);
  if (fields.value !== undefined) return `${fields.value.replace(".", ",")}${NBSP}${test.unit_label}`.trim();
  return "";
}
