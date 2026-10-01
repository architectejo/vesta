/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    // Le parcours de recette Playwright (e2e/, tâche 5.2) a son propre
    // runner (npx playwright test) : jamais ramassé par Vitest, et
    // inversement Playwright ignore src/ (voir playwright.config.ts).
    exclude: ["e2e/**", "node_modules/**"],
    // Les tests saisissent des formulaires entiers avec userEvent : 5 s (défaut)
    // est trop juste quand plusieurs workers jsdom tournent en parallèle.
    testTimeout: 15_000,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.d.ts", "src/routes/dev/**"],
    },
  },
});
