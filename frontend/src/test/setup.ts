import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// Sous charge (workers jsdom en parallèle), la limite par défaut de 1 s des
// findBy… / waitFor est trop juste après une saisie userEvent.
configure({ asyncUtilTimeout: 5000 });

// Nettoie le DOM entre chaque test (Testing Library).
// Le démontage d'une Modal appelle history.back() ; jsdom émet le popstate de
// façon asynchrone. On le laisse arriver avant le test suivant pour qu'il ne
// soit pas pris pour un événement de ce dernier.
afterEach(async () => {
  cleanup();
  await new Promise((resolve) => setTimeout(resolve, 10));
});

// jsdom n'implémente pas matchMedia : nécessaire pour `prefers-reduced-motion`,
// `prefers-color-scheme` et les points de rupture testés en JS.
if (!window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  });
}
