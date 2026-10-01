import { useEffect, useState } from "react";

/**
 * Reflète en direct une media query CSS (ex. `(min-width: 1024px)`).
 * Utilisé pour les largeurs de colonnes qui varient selon le point de
 * rupture (grille des cotisations, `docs/lot0/design-system.md` §3.3 :
 * colonne « Joueur » de 120 px sur mobile, 200 px à partir de 1024 px).
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() =>
    typeof window !== "undefined" ? window.matchMedia(query).matches : false,
  );

  useEffect(() => {
    const mediaQueryList = window.matchMedia(query);
    function handleChange(event: MediaQueryListEvent): void {
      setMatches(event.matches);
    }
    setMatches(mediaQueryList.matches);
    mediaQueryList.addEventListener("change", handleChange);
    return () => mediaQueryList.removeEventListener("change", handleChange);
  }, [query]);

  return matches;
}
