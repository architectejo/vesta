import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../App";
import { AuthProvider } from "../../auth/AuthContext";
import { setSessionTokens, setStoredIdentity } from "../../auth/session";
import { ThemeProvider, ToastProvider } from "../../design-system";

const terms = { id: 7, version_number: 3, content: "Texte des CGU" };

vi.mock("../../api/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/auth")>()),
  forcedPasswordChange: vi.fn().mockResolvedValue({ detail: "ok" }),
  getPendingTerms: vi.fn(),
  acceptTerms: vi.fn().mockResolvedValue({}),
}));

// Les pages ne sont jamais montées tant qu'une modale bloque : on les remplace
// par des bouchons pour que la résolution ne déclenche aucun appel réseau.
vi.mock("../accueil/AccueilPage", () => ({ AccueilPage: () => <div>PAGE-ACCUEIL</div> }));
vi.mock("../club/ComiteBureauPage", () => ({ ComiteBureauPage: () => <div>PAGE-COMITE</div> }));
vi.mock("../sport/VestiairePage", () => ({ VestiairePage: () => <div>PAGE-VESTIAIRE</div> }));
vi.mock("../../layouts/AppLayout", () => ({
  AppLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { acceptTerms, getPendingTerms } from "../../api/auth";

function setup(path: string, opts: { mustChangePassword: boolean; superuser?: boolean }) {
  setSessionTokens({ access: "a1", refresh: "r1" });
  setStoredIdentity({
    user: {
      id: 1,
      email: "j@example.com",
      first_name: "Jean",
      last_name: "K.",
      is_superuser: Boolean(opts.superuser),
      must_change_password: opts.mustChangePassword,
      preferred_theme: "classic",
    },
    club: null,
  });
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ThemeProvider initialTheme="light">
        <ToastProvider>
          <AuthProvider>
            <MemoryRouter initialEntries={[path]}>
              <App />
            </MemoryRouter>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

const ROUTES: Array<[string, string]> = [
  ["/", "PAGE-ACCUEIL"],
  ["/club/comite", "PAGE-COMITE"],
  ["/vestiaire", "PAGE-VESTIAIRE"],
];

describe("Modales bloquantes de premier accès sur toute page protégée", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.mocked(getPendingTerms).mockReset().mockResolvedValue(null);
  });

  it.each(ROUTES)("mot de passe forcé sur %s : une seule modale, page non montée, non fermable", async (path, page) => {
    setup(path, { mustChangePassword: true });
    expect(screen.getAllByRole("heading", { name: "Changez votre mot de passe" })).toHaveLength(1);
    expect(screen.queryByText(page)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Fermer" })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("heading", { name: "Changez votre mot de passe" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Se déconnecter" })).toBeInTheDocument();
  });

  it.each(ROUTES)("CGU sur %s : une seule modale, non fermable, disparaît après acceptation", async (path, page) => {
    vi.mocked(getPendingTerms).mockResolvedValue(terms as never);
    setup(path, { mustChangePassword: false });
    const heading = await screen.findByRole("heading", { name: "Vos données et votre consentement" });
    expect(heading).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Vos données et votre consentement" })).toHaveLength(1);
    expect(screen.queryByText(page)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Fermer" })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("heading", { name: "Vos données et votre consentement" })).toBeInTheDocument();

    vi.mocked(getPendingTerms).mockResolvedValue(null);
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Continuer" }));
    expect(acceptTerms).toHaveBeenCalledWith(7);
    await waitFor(() => expect(screen.getByText(page)).toBeInTheDocument());
    expect(screen.queryByRole("heading", { name: "Vos données et votre consentement" })).not.toBeInTheDocument();
  });

  it("mot de passe forcé : disparaît après résolution sur le Comité", async () => {
    setup("/club/comite", { mustChangePassword: true });
    await userEvent.type(screen.getByLabelText("Nouveau mot de passe"), "unNouveauMotDePasse");
    await userEvent.type(screen.getByLabelText("Confirmez le mot de passe"), "unNouveauMotDePasse");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(screen.getByText("PAGE-COMITE")).toBeInTheDocument());
    expect(screen.queryByRole("heading", { name: "Changez votre mot de passe" })).not.toBeInTheDocument();
  });

  it("espace Superuser : le mot de passe forcé bloque aussi /admin", () => {
    setup("/admin/journal", { mustChangePassword: true, superuser: true });
    expect(screen.getAllByRole("heading", { name: "Changez votre mot de passe" })).toHaveLength(1);
  });
});
