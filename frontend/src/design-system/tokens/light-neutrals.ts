/**
 * Neutres du thème Clair (et donc de Classic) nécessaires aux calculs de
 * contraste à l'exécution (docs/lot0/design-system.md §7.1). Ce sont des
 * couleurs de la plateforme, pas des couleurs de club (règle 18).
 *
 * Ces valeurs doivent rester identiques à `tokens.css` ; `light-neutrals.test.ts`
 * lit le fichier CSS et échoue en cas d'écart.
 */

/** `--color-surface` : cartes, modales, champs, pastille active de la barre latérale. */
export const LIGHT_SURFACE = "#f6f7f9";

/**
 * `--color-surface-muted` : neutre le plus sombre sur lequel un lien peut
 * apparaître (bouton ghost survolé, en-tête de tableau).
 */
export const LIGHT_SURFACE_MUTED = "#e6e9ee";
