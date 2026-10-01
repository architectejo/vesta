import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.tsx";
import { ActiveClubBrandingProvider } from "./auth/ActiveClubBrandingProvider";
import { AuthProvider } from "./auth/AuthContext";
import { ThemeProvider, ToastProvider } from "./design-system";
import "./index.css";

const queryClient = new QueryClient();

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
