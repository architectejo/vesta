import { useLayoutEffect, useState } from "react";

/**
 * Largeur courante d'un élément (graphiques fluides à 100 % du cadre).
 * Retourne un « callback ref » : fonctionne même si l'élément n'est monté
 * qu'après un état de chargement. `fallback` sert avant la première mesure
 * et dans jsdom (sans mise en page).
 */
export function useElementWidth<T extends HTMLElement>(fallback = 320) {
  const [element, setElement] = useState<T | null>(null);
  const [width, setWidth] = useState(fallback);

  useLayoutEffect(() => {
    if (!element) return;
    const update = () => {
      const next = Math.round(element.clientWidth);
      if (next > 0) setWidth(next);
    };
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);

  return [setElement, width] as const;
}
