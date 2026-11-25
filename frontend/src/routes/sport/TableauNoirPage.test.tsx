import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import type { TacticalPlanDetail } from "../../api/sport";
import { ToastProvider } from "../../design-system";
import { TableauNoirPage } from "./TableauNoirPage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn(), listClubPlayers: vi.fn() };
});

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, getTacticalPlan: vi.fn() };
});

import { getMyProfile, listClubPlayers } from "../../api/clubs";
import { getTacticalPlan } from "../../api/sport";

function makeProfile(...roles: string[]): MyProfile {
  return {
    membership_id: 1,
    club: { id: 1, slug: "test", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    identity: {
      first_name: "Jean",
      last_name: "Coach",
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

function makePlan(): TacticalPlanDetail {
  return {
    id: 1,
    name: "Plan A",
    formation: "4-4-2",
    squad_size: 11,
    match_id: null,
    is_published: false,
    published_at: null,
    updated_at: "2026-09-01T00:00:00Z",
    created_at: "2026-09-01T00:00:00Z",
    placements: [],
    annotations: [],
  };
}

function renderPage(initialPath = "/plans/1/tableau") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/plans/:id/tableau" element={<TableauNoirPage />} />
            <Route path="/vestiaire" element={<p>Page des plans</p>} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("TableauNoirPage", () => {
  beforeEach(() => {
    vi.mocked(listClubPlayers).mockResolvedValue([]);
  });

  it("redirige un non-Coach vers l'onglet Plans du Vestiaire", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getTacticalPlan).mockResolvedValue(makePlan());
    renderPage();
    expect(await screen.findByText("Page des plans")).toBeInTheDocument();
  });

  it("affiche le tableau noir pour le Coach", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getTacticalPlan).mockResolvedValue(makePlan());
    renderPage();
    expect(await screen.findByRole("heading", { name: "Plan A" })).toBeInTheDocument();
  });

  it("affiche le système de jeu et le nombre de postes pourvus (constat du client, référence externe)", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getTacticalPlan).mockResolvedValue(makePlan());
    renderPage();
    await screen.findByRole("heading", { name: "Plan A" });
    expect(screen.getByText("Système : 4-4-2")).toBeInTheDocument();
    expect(screen.getByText("0/11 postes pourvus")).toBeInTheDocument();
  });
});
