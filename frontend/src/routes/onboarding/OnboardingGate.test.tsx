import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../../auth/AuthContext";
import { setSessionTokens, setStoredIdentity } from "../../auth/session";
import { ThemeProvider, ToastProvider } from "../../design-system";
import { OnboardingGate } from "./OnboardingGate";

vi.mock("../../api/auth", () => ({
  forcedPasswordChange: vi.fn().mockResolvedValue({ detail: "Mot de passe modifié." }),
  getPendingTerms: vi.fn().mockResolvedValue(null),
}));

vi.mock("../../api/clubs", () => ({
  getMyProfile: vi.fn().mockResolvedValue({
    membership_id: 1,
    club: { id: 1, slug: "c", name: "Club", logo: null },
    identity: {
      first_name: "Jean",
      last_name: "K.",
      photo: "https://example.com/photo.jpg",
      email: "j@example.com",
      phone: "",
      birth_date: null,
      weight_kg: null,
      height_cm: null,
    },
    position: "",
    position_label: "",
    position_detail: "",
    jersey_number: null,
    membership_status: "active",
    membership_status_label: "Inscrit",
    roles: [],
    email_notifications_enabled: false,
  }),
}));

import { forcedPasswordChange } from "../../api/auth";

function renderGate() {
  setSessionTokens({ access: "a1", refresh: "r1" });
  setStoredIdentity({
    user: {
      id: 1,
      email: "j@example.com",
      first_name: "Jean",
      last_name: "K.",
      is_superuser: false,
      must_change_password: true,
      preferred_theme: "classic",
    },
    club: null,
  });

  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider initialTheme="light">
        <ToastProvider>
          <AuthProvider>
            <OnboardingGate>
              <div>PAGE-PROTEGEE</div>
            </OnboardingGate>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("OnboardingGate (CDC 4.1, 7.1 : changement de mot de passe forcé)", () => {
  it("bloque l'accès à la page tant que le mot de passe n'est pas changé", () => {
    renderGate();
    expect(screen.getByRole("heading", { name: "Changez votre mot de passe" })).toBeInTheDocument();
    expect(screen.queryByText("PAGE-PROTEGEE")).not.toBeInTheDocument();
  });

  it("laisse passer vers la page une fois le mot de passe changé", async () => {
    renderGate();
    await userEvent.type(screen.getByLabelText("Nouveau mot de passe"), "unNouveauMotDePasse");
    await userEvent.type(screen.getByLabelText("Confirmez le mot de passe"), "unNouveauMotDePasse");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(forcedPasswordChange).toHaveBeenCalledWith({
      new_password: "unNouveauMotDePasse",
      confirm_password: "unNouveauMotDePasse",
    });

    await waitFor(() => expect(screen.getByText("PAGE-PROTEGEE")).toBeInTheDocument());
  });
});
