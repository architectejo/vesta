import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import { ToastProvider } from "../../design-system";
import { PlansListPage } from "./PlansListPage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, listTacticalPlans: vi.fn() };
});

import { getMyProfile } from "../../api/clubs";
import { listTacticalPlans } from "../../api/sport";

function makeProfile(...roles: string[]): MyProfile {
  return {
    membership_id: 1,
    club: { id: 1, slug: "test", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    identity: {
      first_name: "Jean",
      last_name: "Joueur",
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
    jersey_number: null,
    membership_status: "active",
    membership_status_label: "Inscrit",
    roles: roles.map((role) => ({ role, label: role })),
    email_notifications_enabled: true,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter>
          <PlansListPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("PlansListPage", () => {
  it("n'affiche « Nouveau plan » qu'au Coach", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(listTacticalPlans).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    renderPage();
    expect(await screen.findByText("Aucun plan publié pour l'instant.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nouveau plan" })).not.toBeInTheDocument();
  });

  it("liste les plans avec leur statut", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(listTacticalPlans).mockResolvedValue({
      count: 1,
      next_offset: null,
      results: [
        {
          id: 1,
          name: "Plan A",
          formation: "4-4-2",
          squad_size: 11,
          match_id: null,
          is_published: true,
          published_at: "2026-09-01T00:00:00Z",
          updated_at: "2026-09-01T00:00:00Z",
        },
      ],
    });
    renderPage();
    expect(await screen.findByText("Plan A")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nouveau plan" })).toBeInTheDocument();
  });
});
