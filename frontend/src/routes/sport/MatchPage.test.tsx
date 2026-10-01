import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MyProfile, ClubPlayerListItem } from "../../api/clubs";
import type { MatchDetail } from "../../api/sport";
import { ToastProvider } from "../../design-system";
import { MatchPage } from "./MatchPage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn(), listClubPlayers: vi.fn() };
});

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, getMatch: vi.fn(), listEventIncidents: vi.fn() };
});

import { getMyProfile, listClubPlayers } from "../../api/clubs";
import { getMatch, listEventIncidents } from "../../api/sport";

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

function makeRoster(): ClubPlayerListItem[] {
  return [];
}

function makeMatch(overrides: Partial<MatchDetail> = {}): MatchDetail {
  return {
    id: 5,
    kind: "match",
    event_date: "2026-10-03",
    season_id: 1,
    is_locked: false,
    unlocked_by: null,
    unlocked_at: null,
    unlock_reason: "",
    kickoff_time: "15:00:00",
    opponent: "FC Espoir",
    match_type: "friendly",
    venue: "home",
    location: "",
    challenge_status: "n_a",
    is_composition_published: false,
    composition_published_at: null,
    attendances: [],
    attendance_counts: { present: 0, late: 0, excused: 0, not_marked: 0 },
    starters: [],
    substitutes: [],
    sheet: null,
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/matchs/5"]}>
          <Routes>
            <Route path="/matchs/:id" element={<MatchPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("MatchPage", () => {
  beforeEach(() => {
    vi.mocked(listClubPlayers).mockResolvedValue(makeRoster());
    vi.mocked(listEventIncidents).mockResolvedValue({ count: 0, next_offset: null, results: [] });
  });

  it("propose « Composer l'équipe » au Coach sans composition", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getMatch).mockResolvedValue(makeMatch());
    renderPage();
    // Deux boutons legitimes portent ce libellé (action d'en-tête et action
    // de l'état vide de la carte « Composition ») : on vérifie qu'au moins
    // un existe, sans figer lequel des deux l'emporte.
    expect((await screen.findAllByRole("button", { name: "Composer l'équipe" })).length).toBeGreaterThan(0);
  });

  it("n'affiche aucune action de gestion pour un simple joueur", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
    vi.mocked(getMatch).mockResolvedValue(makeMatch());
    renderPage();
    expect(await screen.findByText("Club de test – FC Espoir")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Composer l'équipe" })).not.toBeInTheDocument();
  });
});
