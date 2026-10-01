import { useEffect, useRef, useState } from "react";

const DEFAULT_DELAY_MS = 200;
const DEFAULT_MIN_DURATION_MS = 300;

export interface UseDelayedVisibleOptions {
  /** Délai avant apparition de l'indicateur (évite le clignotement, 3.5). */
  delayMs?: number;
  /** Durée minimale d'affichage une fois apparu (3.5). */
  minDurationMs?: number;
}

/**
 * Retarde l'affichage d'un indicateur de chargement de `delayMs` (200 ms par
 * défaut) pour ne pas clignoter sur une réponse rapide, puis le maintient au
 * moins `minDurationMs` (300 ms) une fois apparu (docs/lot0/design-system.md
 * §3.5 « Délais »).
 */
export function useDelayedVisible(
  loading: boolean,
  options: UseDelayedVisibleOptions = {},
): boolean {
  const { delayMs = DEFAULT_DELAY_MS, minDurationMs = DEFAULT_MIN_DURATION_MS } = options;
  const [visible, setVisible] = useState(false);
  const shownAtRef = useRef<number | null>(null);

  useEffect(() => {
    if (!loading) {
      if (shownAtRef.current === null) {
        setVisible(false);
        return;
      }
      const elapsed = Date.now() - shownAtRef.current;
      const remaining = Math.max(0, minDurationMs - elapsed);
      const hideTimer = window.setTimeout(() => {
        setVisible(false);
        shownAtRef.current = null;
      }, remaining);
      return () => window.clearTimeout(hideTimer);
    }

    const showTimer = window.setTimeout(() => {
      shownAtRef.current = Date.now();
      setVisible(true);
    }, delayMs);

    return () => window.clearTimeout(showTimer);
  }, [loading, delayMs, minDurationMs]);

  return visible;
}
