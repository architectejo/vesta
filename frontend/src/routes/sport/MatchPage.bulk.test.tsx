import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ClubPlayerListItem, MyProfile } from "../../api/clubs";
import type { AttendanceCapabilities, MatchDetail } from "../../api/sport";
import { ToastProvider } from "../../design-system";
import { MatchPage } from "./MatchPage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn(), listClubPlayers: vi.fn() };
});

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, getMatch: vi.fn(), listEventIncidents: vi.fn(), bulkMarkAttendance: vi.fn() };
});

vi.mock("../../api/logistics", async () => {
  const actual = await vi.importActual<typeof import("../../api/logistics")>("../../api/logistics");
  return { ...actual, getMatchEquipment: vi.fn().mockResolvedValue({ lines: [] }) };
});

import { getMyProfile, listClubPlayers } from "../../api/clubs";
import { bulkMarkAttendance, getMatch, listEventIncidents } from "../../api/sport";

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

function player(id: number, first: string, last: string): ClubPlayerListItem {
  return {
    membership_id: id,
    first_name: first,
    last_name: last,
    photo: null,
    position: "midfielder",
    position_label: "Milieu",
    position_detail: "",
    jersey_number: id,
    membership_status: "active",
    membership_status_label: "Inscrit",
    roles: [],
  };
}

function makeMatch(capabilities: AttendanceCapabilities | undefined): MatchDetail {
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
    attendance_counts: { present: 0, late: 0, excused: 0, not_marked: 2 },
    starters: [],
    substitutes: [],
    sheet: null,
    capabilities,
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

describe("MatchPage — pointage groupé", () => {
  beforeEach(() => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(listClubPlayers).mockResolvedValue([player(10, "Paul", "Ilunga"), player(11, "Anne", "Kasa")]);
    vi.mocked(listEventIncidents).mockResolvedValue({ count: 0, next_offset: null, results: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("masque « Sélectionner » sans capacité", async () => {
    vi.mocked(getMatch).mockResolvedValue(
      makeMatch({ can_bulk_mark: false, can_bulk_excuse: false, can_set_arrival_time: false }),
    );
    renderPage();
    expect(await screen.findByText("Club de test – FC Espoir")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sélectionner" })).not.toBeInTheDocument();
  });

  it("coche tout, confirme puis envoie le lot au bon point d'accès (match)", async () => {
    const user = userEvent.setup();
    vi.mocked(getMatch).mockResolvedValue(
      makeMatch({ can_bulk_mark: true, can_bulk_excuse: true, can_set_arrival_time: true }),
    );
    vi.mocked(bulkMarkAttendance).mockResolvedValue({
      batch_id: "b",
      results: [
        { membership_id: 10, outcome: "created", message: "", attendance: null },
        { membership_id: 11, outcome: "created", message: "", attendance: null },
      ],
      counts: { created: 2, skipped: 0, refused: 0 },
    });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Sélectionner" }));
    await user.click(screen.getByRole("button", { name: "Tout cocher (2)" }));
    expect(screen.getByText("2 sélectionnés")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Absent excusé" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Pointer l'arrivée (2)" }));
    expect(bulkMarkAttendance).not.toHaveBeenCalled();
    await user.click(await screen.findByRole("button", { name: "Pointer (2)" }));

    await waitFor(() => expect(bulkMarkAttendance).toHaveBeenCalledTimes(1));
    const [kind, eventId, body] = vi.mocked(bulkMarkAttendance).mock.calls[0]!;
    expect(kind).toBe("match");
    expect(eventId).toBe(5);
    expect(body.items.map((i) => [i.membership_id, i.selection_rank])).toEqual([
      [10, 1],
      [11, 2],
    ]);
  });
});
