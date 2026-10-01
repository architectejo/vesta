import { defineConfig, devices } from "@playwright/test";

/**
 * Parcours de recette bout en bout (CDC 9.3, tâche 5.2 du plan des lots).
 *
 * Mobile-first (CLAUDE.md §2.16) : le viewport par défaut est 360 px de
 * large, conformément à la charte du chapitre 3. Les serveurs de dev
 * (backend Django sur :8000, frontend Vite sur :5173) sont supposés déjà
 * démarrés (`python manage.py runserver`, `npm run dev`) — cette config ne
 * tente pas de les démarrer elle-même pour rester simple à relancer en
 * boucle pendant la mise au point.
 */
export default defineConfig({
  testDir: "./e2e",
  // Chaque connexion (`loginAs`) démarre un process Python/Django complet
  // (`manage.py issue_e2e_session`, ~7-20 s) : plusieurs par étape du
  // scénario 9.3 dépassent largement le délai par défaut de Playwright.
  timeout: 150_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  // Une relance automatique absorbe la flakiness d'un poste de dev
  // partagé (compilation Vite, charge du navigateur réel de
  // l'utilisateur) sans masquer un vrai défaut du produit -- un défaut
  // réel échoue de façon répétée, pas une seule fois sur dix.
  retries: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.E2E_FRONTEND_URL ?? "http://localhost:5173",
    viewport: { width: 360, height: 740 },
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium-360",
      use: { ...devices["Desktop Chrome"], viewport: { width: 360, height: 740 } },
    },
  ],
});
