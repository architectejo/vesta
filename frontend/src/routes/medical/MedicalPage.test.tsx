import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { ToastProvider } from "../../design-system";
import { MedicalPage } from "./MedicalPage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn(), listClubPlayers: vi.fn() };
});

vi.mock("../../api/medical", async () => {
  const actual = await vi.importActual<typeof import("../../api/medical")>("../../api/medical");
  return {
    ...actual,
    listInjuriesToComplete: vi.fn(),
    listRecentInjuries: vi.fn(),
    listUnfitAndRestricted: vi.fn(),
  };
});

import { getMyProfile, listClubPlayers } from "../../api/clubs";
import { listInjuriesToComplete, listRecentInjuries, listUnfitAndRestricted } from "../../api/medical";

function baseProfile(roles: Array<{ role: string; label: string }>) {
  return {
    membership_id: 1,
    club: { id: 1, slug: "club", name: "Club Test", logo: null },
    identity: {
      first_name: "Jean",
      last_name: "Kabila",
      photo: null,
      email: "jean@example.com",
      phone: "",
      birth_date: null,
      weight_kg: null,
      height_cm: null,
    },
    position: "midfielder",
    position_label: "Milieu",
    position_detail: "",
    jersey_number: 10,
    membership_status: "active",
    membership_status_label: "Actif",
    roles,
    email_notifications_enabled: true,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>
          <MedicalPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("MedicalPage (medical.md §3)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche l'état vide unique quand l'API refuse l'accès (rôle non autorisé)", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(baseProfile([{ role: "member", label: "Joueur" }]) as never);
    vi.mocked(listUnfitAndRestricted).mockRejectedValue(new ApiError(403, { detail: "Vous n'avez pas accès à cette action." }));

    renderPage();

    expect(await screen.findByText("Vous n'avez pas accès à cette page.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retour à l'accueil" })).toBeInTheDocument();
  });

  it("Médecin : affiche « Blessures à compléter », « Effectif » et « Dernières blessures »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(baseProfile([{ role: "doctor", label: "Médecin / référent santé" }]) as never);
    vi.mocked(listUnfitAndRestricted).mockResolvedValue({ results: [] });
    vi.mocked(listInjuriesToComplete).mockResolvedValue({ results: [], next_offset: null });
    vi.mocked(listRecentInjuries).mockResolvedValue({ results: [] });
    vi.mocked(listClubPlayers).mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("Blessures à compléter")).toBeInTheDocument();
    expect(screen.getByText("Effectif")).toBeInTheDocument();
    expect(screen.getByText("Dernières blessures")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Déclarer une blessure" }).length).toBeGreaterThan(0);
  });

  it("Coach : n'affiche ni « Blessures à compléter » ni « Effectif », seulement « Inaptes et restrictions »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(baseProfile([{ role: "coach", label: "Coach" }]) as never);
    vi.mocked(listUnfitAndRestricted).mockResolvedValue({ results: [] });

    renderPage();

    expect(await screen.findByText("Inaptes et restrictions")).toBeInTheDocument();
    expect(screen.queryByText("Blessures à compléter")).not.toBeInTheDocument();
    expect(screen.queryByText("Effectif")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Déclarer une blessure" })).toBeInTheDocument();
  });
});
