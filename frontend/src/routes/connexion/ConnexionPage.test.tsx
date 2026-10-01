import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { AuthProvider } from "../../auth/AuthContext";
import { clearSessionTokens } from "../../auth/session";
import { ThemeProvider, ToastProvider } from "../../design-system";
import { ConnexionPage } from "./ConnexionPage";

vi.mock("../../api/auth", () => ({
  login: vi.fn(),
  requestPasswordReset: vi.fn(),
}));

import { login } from "../../api/auth";

function renderPage(initialEntry = "/connexion") {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider initialTheme="light">
        <ToastProvider>
          <MemoryRouter initialEntries={[initialEntry]}>
            <AuthProvider>
              <Routes>
                <Route path="/connexion" element={<ConnexionPage />} />
                <Route path="/" element={<div>ACCUEIL-TEST</div>} />
              </Routes>
            </AuthProvider>
          </MemoryRouter>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("ConnexionPage", () => {
  beforeEach(() => {
    vi.mocked(login).mockReset();
  });

  afterEach(() => {
    clearSessionTokens();
  });

  it("affiche la présentation neutre, sans nom de club en dur", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "Connexion" })).toBeInTheDocument();
    expect(screen.getByText("Vesta")).toBeInTheDocument();
    expect(screen.getByText("Accédez à l'espace de votre club.")).toBeInTheDocument();
  });

  it("affiche les erreurs de champs obligatoires", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(screen.getByText("Ce champ est obligatoire.")).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("redirige vers l'accueil après une connexion réussie", async () => {
    vi.mocked(login).mockResolvedValue({
      access: "a",
      refresh: "r",
      user: {
        id: 1,
        email: "joueur@example.com",
        first_name: "Jean",
        last_name: "K.",
        is_superuser: false,
        must_change_password: false,
        preferred_theme: "classic",
      },
      club: { id: 1, slug: "mon-club", name: "Mon club", logo: null, primary_color: "", secondary_color: "" },
      must_change_password: false,
      terms_acceptance_required: false,
    });

    renderPage();
    await userEvent.type(screen.getByLabelText("Email"), "joueur@example.com");
    await userEvent.type(screen.getByLabelText("Mot de passe"), "motdepasse");
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));

    await waitFor(() => expect(screen.getByText("ACCUEIL-TEST")).toBeInTheDocument());
  });

  it("affiche le message d'identifiants incorrects", async () => {
    vi.mocked(login).mockRejectedValue(
      new ApiError(401, { code: "invalid_credentials", detail: "Email ou mot de passe incorrect." }),
    );

    renderPage();
    await userEvent.type(screen.getByLabelText("Email"), "joueur@example.com");
    await userEvent.type(screen.getByLabelText("Mot de passe"), "mauvais");
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));

    expect(await screen.findByText("Email ou mot de passe incorrect.")).toBeInTheDocument();
  });
});
