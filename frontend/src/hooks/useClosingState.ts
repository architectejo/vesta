import { useEffect, useRef, useState } from "react";

export interface ClosingState {
  /** Faux une fois l'animation de sortie terminée : ne plus rien rendre. */
  mounted: boolean;
  /** À poser sur l'élément animé (`data-state`), docs/lot0/design-system-icones-animations.md §2.2. */
  dataState: "open" | "closing";
  /** À passer à `onAnimationEnd` de l'élément animé. */
  onAnimationEnd: () => void;
}

/**
 * Anime la fermeture d'une surface (menu, tiroir, toast…) qui serait sinon
 * démontée instantanément dès que `open` devient faux (design system
 * §2.2) : l'élément reste monté pendant l'animation de sortie, puis se
 * démonte à `animationend`, avec un délai de secours si l'événement ne
 * vient pas (mouvement réduit, par exemple).
 */
export function useClosingState(open: boolean, fallbackMs = 200): ClosingState {
  const [closing, setClosing] = useState(false);
  const wasOpenRef = useRef(open);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (wasOpenRef.current && !open) {
      setClosing(true);
      timerRef.current = setTimeout(() => setClosing(false), fallbackMs);
    } else if (!wasOpenRef.current && open) {
      setClosing(false);
      if (timerRef.current) clearTimeout(timerRef.current);
    }
    wasOpenRef.current = open;
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [open, fallbackMs]);

  return {
    mounted: open || closing,
    dataState: open ? "open" : "closing",
    onAnimationEnd: () => setClosing(false),
  };
}
