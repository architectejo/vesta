import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import App from "./App";
import { ActiveClubBrandingProvider } from "./auth/ActiveClubBrandingProvider";
import { AuthProvider } from "./auth/AuthContext";
import { clearSessionTokens } from "./auth/session";
import { ThemeProvider, ToastProvider } from "./design-system";

// Même imbrication que `main.tsx` (`AuthProvider` puis
// `ActiveClubBrandingProvider` ancêtres de `ThemeProvider`) : ces tests ne
// portent pas sur le branding, mais une imbrication différente de la vraie
// avait précédemment masqué un bug structurel (voir
// `auth/ActiveClubBrandingProvider.test.tsx`).
function renderApp(initialEntry: string) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <ToastProvider>
          <AuthProvider>
            <ActiveClubBrandingProvider>
              <ThemeProvider initialTheme="light">
                <App />
              </ThemeProvider>
            </ActiveClubBrandingProvider>
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App", () => {
  afterEach(() => {
    clearSessionTokens();
  });

  it("redirige un visiteur anonyme vers la connexion sur la route racine", () => {
    renderApp("/");
    expect(screen.getByRole("heading", { name: "Connexion" })).toBeInTheDocument();
  });

  it("affiche la page de démonstration du design system sur /dev/design-system", () => {
    renderApp("/dev/design-system");
    expect(
      screen.getByRole("heading", { name: "Design system Vesta — démonstration interne" }),
    ).toBeInTheDocument();
  });

  it("affiche un état neutre pour une route inconnue", () => {
    renderApp("/route-inexistante");
    expect(screen.getByText("Cet élément n'existe plus.")).toBeInTheDocument();
  });

  it("affiche la présentation neutre de connexion (pas de nom de club en dur)", () => {
    renderApp("/connexion");
    expect(screen.getByRole("heading", { name: "Connexion" })).toBeInTheDocument();
    expect(screen.getByText("Vesta")).toBeInTheDocument();
  });
});
