/**
 * Utilitaires de contraste WCAG, utilisés pour dériver les couleurs
 * d'accent du thème Classic à partir des couleurs du club fournies par
 * l'API (docs/lot0/design-system.md §2.4).
 *
 * Aucune couleur de club n'est écrite en dur ici : ces fonctions ne font
 * que transformer une couleur reçue en entrée.
 */

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

const HEX_RE = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i;

/** Convertit une couleur hexadécimale (#RGB ou #RRGGBB) en composantes RVB. */
export function hexToRgb(hex: string): Rgb | null {
  const match = HEX_RE.exec(hex.trim());
  if (!match) return null;
  let value = match[1];
  if (!value) return null;
  if (value.length === 3) {
    value = value
      .split("")
      .map((c) => c + c)
      .join("");
  }
  const num = Number.parseInt(value, 16);
  return {
    r: (num >> 16) & 255,
    g: (num >> 8) & 255,
    b: num & 255,
  };
}

export function rgbToHex({ r, g, b }: Rgb): string {
  const toHex = (n: number): string =>
    Math.round(clamp(n, 0, 255))
      .toString(16)
      .padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function channelToLinear(channel: number): number {
  const c = channel / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** Luminance relative (WCAG 2.x), 0 (noir) à 1 (blanc). */
export function relativeLuminance(color: Rgb): number {
  const r = channelToLinear(color.r);
  const g = channelToLinear(color.g);
  const b = channelToLinear(color.b);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Ratio de contraste WCAG entre deux couleurs (1 à 21). */
export function contrastRatio(a: Rgb, b: Rgb): number {
  const l1 = relativeLuminance(a);
  const l2 = relativeLuminance(b);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

const WHITE: Rgb = { r: 255, g: 255, b: 255 };
const DARK: Rgb = { r: 17, g: 24, b: 39 }; // #111827

/** Choisit blanc ou `#111827` selon le meilleur contraste sur `bg`. */
export function pickReadableOnColor(bg: Rgb): Rgb {
  const contrastWithWhite = contrastRatio(bg, WHITE);
  const contrastWithDark = contrastRatio(bg, DARK);
  return contrastWithWhite >= contrastWithDark ? WHITE : DARK;
}

function mixToward(color: Rgb, target: Rgb, amount: number): Rgb {
  return {
    r: color.r + (target.r - color.r) * amount,
    g: color.g + (target.g - color.g) * amount,
    b: color.b + (target.b - color.b) * amount,
  };
}

const MAX_STEPS = 20;
const STEP = 0.05;

/**
 * Assombrit `bg` par pas de 5 % vers le noir jusqu'à ce que le contraste
 * avec `fg` atteigne `target` (par défaut 4.5:1), ou jusqu'à 20 pas.
 */
export function darkenUntilContrast(bg: Rgb, fg: Rgb, target = 4.5): Rgb {
  let candidate = bg;
  for (let step = 0; step < MAX_STEPS; step += 1) {
    if (contrastRatio(candidate, fg) >= target) return candidate;
    candidate = mixToward(candidate, { r: 0, g: 0, b: 0 }, STEP);
  }
  return candidate;
}

export interface AccentPair {
  /** Fond (couleur du club, éventuellement assombrie pour la lisibilité). */
  bg: string;
  /** Texte sur ce fond : blanc ou `#111827`. */
  fg: string;
}

/**
 * Dérive un couple fond/texte lisible (≥ 4.5:1) à partir d'une couleur de
 * club brute. Utilisé pour `--color-sidebar-bg`/`--color-sidebar-text` et
 * `--color-primary`/`--color-on-primary` (2.4).
 */
export function deriveAccentPair(rawHex: string, target = 4.5): AccentPair | null {
  const raw = hexToRgb(rawHex);
  if (!raw) return null;
  const fg = pickReadableOnColor(raw);
  const bg = contrastRatio(raw, fg) >= target ? raw : darkenUntilContrast(raw, fg, target);
  return { bg: rgbToHex(bg), fg: rgbToHex(fg) };
}

/**
 * Assombrit une couleur de club jusqu'à ce qu'elle soit lisible en tant que
 * texte sur `surfaceHex` (`--color-primary-text`, liens).
 *
 * `surfaceHex` est obligatoire : il n'existe plus de blanc pur dans les
 * neutres de la plateforme (7.1). Passer le neutre le plus sombre sur lequel
 * un lien peut apparaître (`--color-surface-muted`), voir `light-neutrals.ts`.
 */
export function deriveReadableTextColor(
  rawHex: string,
  surfaceHex: string,
  target = 4.5,
): string | null {
  const raw = hexToRgb(rawHex);
  const surface = hexToRgb(surfaceHex);
  if (!raw || !surface) return null;
  const adjusted =
    contrastRatio(raw, surface) >= target ? raw : darkenUntilContrast(raw, surface, target);
  return rgbToHex(adjusted);
}

/**
 * Accent non textuel (liseré, anneau d'avatar) : la couleur brute du club
 * est conservée si elle atteint 3:1 sur `surfaceHex` (seuil WCAG 1.4.11 pour
 * les composants graphiques), sinon elle est assombrie (7.2).
 */
export function deriveAccentOnSurface(
  rawHex: string,
  surfaceHex: string,
  target = 3,
): string | null {
  const raw = hexToRgb(rawHex);
  const surface = hexToRgb(surfaceHex);
  if (!raw || !surface) return null;
  const adjusted =
    contrastRatio(raw, surface) >= target ? raw : darkenUntilContrast(raw, surface, target);
  return rgbToHex(adjusted);
}

export interface ClassicSidebarTokens {
  textMuted: string;
  hoverBg: string;
  activeBg: string;
  activeText: string;
}

const MUTED_MIX = 0.3;
const HOVER_MIX = 0.1;
const MIX_STEP = 0.05;

/**
 * Dérive les quatre tokens de barre latérale du thème Classic à partir des
 * couleurs déjà calculées (7.2) :
 * - texte secondaire = `sidebarText` mélangé à 30 % vers `sidebarBg`, réduit
 *   par pas de 5 % tant que le contraste avec `sidebarBg` est sous 4,5:1 ;
 * - survol = `sidebarBg` mélangé à 10 % vers `sidebarText`, réduit tant que
 *   `sidebarText` y est sous 4,5:1 ;
 * - élément actif = pastille claire (`surfaceHex`) et texte `primaryText`.
 */
export function deriveClassicSidebarTokens(input: {
  sidebarBg: string;
  sidebarText: string;
  primaryText: string;
  surfaceHex: string;
}): ClassicSidebarTokens | null {
  const bg = hexToRgb(input.sidebarBg);
  const text = hexToRgb(input.sidebarText);
  const surface = hexToRgb(input.surfaceHex);
  const primaryText = hexToRgb(input.primaryText);
  if (!bg || !text || !surface || !primaryText) return null;

  let muted = text;
  for (let amount = MUTED_MIX; amount > 0; amount -= MIX_STEP) {
    const candidate = mixToward(text, bg, amount);
    if (contrastRatio(candidate, bg) >= 4.5) {
      muted = candidate;
      break;
    }
  }

  let hover = bg;
  for (let amount = HOVER_MIX; amount > 0.001; amount -= MIX_STEP) {
    const candidate = mixToward(bg, text, amount);
    if (contrastRatio(candidate, text) >= 4.5) {
      hover = candidate;
      break;
    }
  }

  return {
    textMuted: rgbToHex(muted),
    hoverBg: rgbToHex(hover),
    activeBg: rgbToHex(surface),
    activeText: rgbToHex(primaryText),
  };
}

export interface PlayerCardTokens {
  from: string;
  to: string;
  fg: string;
  fgMuted: string;
  bandBg: string;
  bandFg: string;
  frame: string;
  frameHighlight: string;
}

const BLACK: Rgb = { r: 0, g: 0, b: 0 };
const BAND_STEP = 0.05;
const BAND_MAX_AMOUNT = 1;
const MUTED_TARGET_MIX = 0.2;
const MUTED_STEP = 0.05;
const FRAME_HIGHLIGHT_MIX = 0.4;

/**
 * Dérive les huit tokens de la carte de joueur (docs/ecrans/club-carte-joueur.md
 * A6) à partir de la couleur primaire du club et de l'accent déjà calculé
 * (`--color-accent`, même formule que la barre latérale, §7.2). Retourne
 * `null` si `primaryHex` est invalide : le composant appelant doit alors
 * garder les valeurs par défaut de `tokens.css` (Clair).
 */
export function derivePlayerCardTokens(input: {
  primaryHex: string;
  /** `--color-accent` déjà dérivé (secondaire du club, ou primaire à défaut) ; `null` si indérivable. */
  accentHex: string | null;
}): PlayerCardTokens | null {
  const pair = deriveAccentPair(input.primaryHex);
  if (!pair) return null;
  const fromRgb = hexToRgb(pair.bg);
  const fgRgb = hexToRgb(pair.fg);
  if (!fromRgb || !fgRgb) return null;

  // 1-2. `to` s'éloigne toujours de la couleur du texte : si le texte est
  // clair (blanc), on assombrit ; si le texte est foncé, on éclaircit.
  const fgIsLight = relativeLuminance(fgRgb) > 0.5;
  const awayTarget = fgIsLight ? BLACK : WHITE;
  const toRgb = mixToward(fromRgb, awayTarget, 0.3);

  // 3. `band-bg` : `to` poussé encore de 15 % dans le même sens ; ≥ 7:1 visé,
  // sinon on pousse par pas de 5 % supplémentaires.
  let bandAmount = 0.15;
  let bandBgRgb = mixToward(toRgb, awayTarget, bandAmount);
  while (contrastRatio(bandBgRgb, fgRgb) < 7 && bandAmount < BAND_MAX_AMOUNT) {
    bandAmount = Math.min(bandAmount + BAND_STEP, BAND_MAX_AMOUNT);
    bandBgRgb = mixToward(toRgb, awayTarget, bandAmount);
  }

  // 4. `fg-muted` : `fg` mélangé à 20 % vers `from`, contrôlé ≥ 4,5:1 sur
  // `from` ET sur `to` ; sinon réduit le mélange par pas de 5 %.
  let mutedAmount = MUTED_TARGET_MIX;
  let mutedRgb = mixToward(fgRgb, fromRgb, mutedAmount);
  while (
    (contrastRatio(mutedRgb, fromRgb) < 4.5 || contrastRatio(mutedRgb, toRgb) < 4.5) &&
    mutedAmount > 0
  ) {
    mutedAmount = Math.max(mutedAmount - MUTED_STEP, 0);
    mutedRgb = mixToward(fgRgb, fromRgb, mutedAmount);
  }

  // 5. `frame` = accent déjà calculé (repli sur `from` si indisponible) ;
  // `frame-highlight` = `frame` mélangé à 40 % vers le blanc.
  const frameRgb = (input.accentHex ? hexToRgb(input.accentHex) : null) ?? fromRgb;
  const frameHighlightRgb = mixToward(frameRgb, WHITE, FRAME_HIGHLIGHT_MIX);

  return {
    from: rgbToHex(fromRgb),
    to: rgbToHex(toRgb),
    fg: rgbToHex(fgRgb),
    fgMuted: rgbToHex(mutedRgb),
    bandBg: rgbToHex(bandBgRgb),
    bandFg: rgbToHex(fgRgb),
    frame: rgbToHex(frameRgb),
    frameHighlight: rgbToHex(frameHighlightRgb),
  };
}
