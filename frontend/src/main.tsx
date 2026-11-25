import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { createQueryClient } from "./api/queryClient";
import App from "./App.tsx";
import { ActiveClubBrandingProvider } from "./auth/ActiveClubBrandingProvider";
import { AuthProvider } from "./auth/AuthContext";
import { getAccessToken, getStoredIdentity, subscribeToSession } from "./auth/session";
import { ThemeProvider, ToastProvider } from "./design-system";
import "./index.css";

const queryClient = createQueryClient();

// Le cache TanStack Query ne doit jamais survivre à la session qui l'a rempli
// (CDC 7.1) : sur un téléphone partagé, les rôles et les soldes du Trésorier
// ne doivent pas s'afficher pour le joueur suivant. On vide le cache dès que
// la session disparaît ou que l'identité connectée change.
// L'identité stockée vient du navigateur : on ne présume pas de sa forme
// (ancienne version, valeur tronquée) pour ne jamais planter au démarrage.
let lastSessionUserId: number | null = getStoredIdentity()?.user?.id ?? null;
subscribeToSession(() => {
  const currentUserId = getAccessToken() ? (getStoredIdentity()?.user?.id ?? null) : null;
  if (currentUserId !== lastSessionUserId) {
    queryClient.clear();
  }
  lastSessionUserId = currentUserId;
});

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Élément #root introuvable dans index.html.");
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/*
          `AuthProvider` doit être ancêtre de `ThemeProvider` :
          `ActiveClubBrandingProvider` lit la session (`useAuth`) et le profil
          courant pour poser le `ClubBrandingProvider` que `ThemeProvider`
          consulte pour dériver les variables CSS globales du thème Classic
          (7.2). Sans session (page de connexion) ou en espace Superuser,
          il fournit une marque neutre : `ThemeProvider` retombe alors sur
          les neutres du thème Clair (2.4) — jamais de marque blanche hors
          club (CLAUDE.md §2 n°18/19).
        */}
        <ToastProvider>
          <AuthProvider>
            <ActiveClubBrandingProvider>
              <ThemeProvider>
                <App />
              </ThemeProvider>
            </ActiveClubBrandingProvider>
          </AuthProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
