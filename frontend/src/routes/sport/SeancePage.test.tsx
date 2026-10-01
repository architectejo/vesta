import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MyProfile, ClubPlayerListItem } from "../../api/clubs";
import { ApiError } from "../../api/client";
import type { SessionDetail, TeamAssignmentItem } from "../../api/sport";
import { ToastProvider } from "../../design-system";
import { SeancePage } from "./SeancePage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn(), listClubPlayers: vi.fn() };
});

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return {
    ...actual,
    getSession: vi.fn(),
    markSessionAttendance: vi.fn(),
    listEventIncidents: vi.fn(),
    listEventEvaluations: vi.fn(),
    assignTeam: vi.fn(),
    setTeamFormation: vi.fn(),
    placeTeamPlayer: vi.fn(),
  };
});

import {
  assignTeam,
  getSession,
  listEventEvaluations,
  listEventIncidents,
  markSessionAttendance,
  placeTeamPlayer,
  setTeamFormation,
} from "../../api/sport";
import { getMyProfile, listClubPlayers } from "../../api/clubs";

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
  return [
    {
      membership_id: 10,
      first_name: "Paul",
      last_name: "Ilunga",
      photo: null,
      position: "midfielder",
      position_label: "Milieu",
      position_detail: "",
      jersey_number: 8,
      membership_status: "active",
      membership_status_label: "Inscrit",
      roles: [],
    },
  ];
}

function makeSession(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return {
    id: 1,
    kind: "session",
    event_date: "2026-09-27",
    season_id: 1,
    is_locked: false,
    unlocked_by: null,
    unlocked_at: null,
    unlock_reason: "",
    gathering_time: "07:30:00",
    late_arrival_cutoff: "08:00:00",
    location: "Terrain A",
    team_a_color: "#1d4ed8",
    team_b_color: "#dc2626",
    team_a_formation: "",
    team_b_formation: "",
    instructions: "",
    late_arrival_counts_absent: true,
    counts: { present: 0, late: 0, excused: 0, not_marked: 1 },
    attendances: [],
    team_a: [],
    team_b: [],
    unassigned: { to_place_manually: [], cannot_play: [] },
    ...overrides,
  };
}

function makeTeamAssignment(overrides: Partial<TeamAssignmentItem> = {}): TeamAssignmentItem {
  return {
    id: 100,
    membership_id: 10,
    player: { membership_id: 10, name: "Paul Ilunga", jersey_number: 8, position: "midfielder", position_label: "Milieu", photo: null },
    team: "A",
    arrival_order: 1,
    is_on_field: false,
    x_coord: null,
    y_coord: null,
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/seances/1"]}>
          <Routes>
            <Route path="/seances/:id" element={<SeancePage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("SeancePage", () => {
  beforeEach(() => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(listClubPlayers).mockResolvedValue(makeRoster());
    vi.mocked(getSession).mockResolvedValue(makeSession());
    vi.mocked(listEventIncidents).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(listEventEvaluations).mockResolvedValue({ results: [], averages: {}, is_locked: false, locks_at: "" });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche la liste de pointage et pointe un joueur en un appui (Coach)", async () => {
    const user = userEvent.setup();
    vi.mocked(markSessionAttendance).mockResolvedValue({
      id: 1,
      membership_id: 10,
      player: { membership_id: 10, name: "Paul Ilunga", jersey_number: 8, position: "midfielder", position_label: "Milieu", photo: null },
      status: "present",
      status_label: "Présent",
      arrived_at: new Date().toISOString(),
      excused_reason: "",
      marked_by: null,
      client_uuid: null,
    });

    renderPage();

    // La bascule par défaut dépend de l'heure réelle par rapport à la
    // limite d'arrivée (§6) : on force l'onglet « Pointage » pour que le
    // test ne dépende pas de l'heure d'exécution.
    await user.click(await screen.findByRole("tab", { name: "Pointage" }));
    expect(await screen.findByText("Paul Ilunga")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Arrivé" }));

    await waitFor(() => expect(markSessionAttendance).toHaveBeenCalledWith(1, expect.objectContaining({ membership_id: 10 })));
  });

  it("affiche le badge « Verrouillée » et retire le bouton Arrivé quand la séance est verrouillée", async () => {
    const user = userEvent.setup();
    vi.mocked(getSession).mockResolvedValue(makeSession({ is_locked: true }));
    renderPage();

    await user.click(await screen.findByRole("tab", { name: "Pointage" }));
    expect(await screen.findByText("Paul Ilunga")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Arrivé" })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Équipes A/B : terrain + banc, plafond de 11, formation par équipe,
// glisser-déposer avec échange (extension client du 30/09/2026, hors CDC
// écrit à ce jour — voir le compte rendu de cette tâche).
// ---------------------------------------------------------------------------

describe("SeancePage — Équipes A/B (terrain, banc, formation)", () => {
  beforeEach(() => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(listClubPlayers).mockResolvedValue(makeRoster());
    vi.mocked(listEventIncidents).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(listEventEvaluations).mockResolvedValue({ results: [], averages: {}, is_locked: false, locks_at: "" });
    vi.mocked(assignTeam).mockResolvedValue(makeTeamAssignment());
    vi.mocked(setTeamFormation).mockResolvedValue(makeSession());
    vi.mocked(placeTeamPlayer).mockResolvedValue(makeSession());
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  async function openEquipesTab(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("tab", { name: "Équipes A/B" }));
  }

  it("choisit la formation de l'équipe A indépendamment de l'équipe B", async () => {
    const user = userEvent.setup();
    vi.mocked(getSession).mockResolvedValue(makeSession({ team_b_formation: "4-3-3" }));
    renderPage();
    await openEquipesTab(user);

    const selects = await screen.findAllByRole("combobox");
    expect(selects).toHaveLength(2);
    expect((selects[1] as HTMLSelectElement).value).toBe("4-3-3");

    await user.selectOptions(selects[0] as HTMLSelectElement, "4-3-3");

    await waitFor(() =>
      expect(setTeamFormation).toHaveBeenCalledWith(1, { team: "A", formation: "4-3-3" }),
    );
  });

  it("place un joueur du banc sur le terrain en l'échangeant avec un coéquipier déjà placé (toucher)", async () => {
    const user = userEvent.setup();
    vi.mocked(getSession).mockResolvedValue(
      makeSession({
        team_a: [
          makeTeamAssignment({
            id: 1,
            membership_id: 10,
            player: { membership_id: 10, name: "Paul Ilunga", jersey_number: 8, position: "midfielder", position_label: "Milieu", photo: null },
            is_on_field: true,
            x_coord: "50.00",
            y_coord: "50.00",
          }),
          makeTeamAssignment({
            id: 2,
            membership_id: 11,
            player: { membership_id: 11, name: "Marc Tshibangu", jersey_number: 4, position: "defender", position_label: "Défenseur", photo: null },
            is_on_field: false,
            x_coord: null,
            y_coord: null,
          }),
        ],
      }),
    );
    renderPage();
    await openEquipesTab(user);

    // Banc : toucher le joueur l'arme, puis « Placer sur le terrain ».
    await user.click(await screen.findByRole("button", { name: "Marc T." }));
    await user.click(await screen.findByRole("button", { name: "Placer sur le terrain" }));
    expect(await screen.findByText(/Touchez un emplacement libre/)).toBeInTheDocument();

    // Toucher le coéquipier déjà sur le terrain échange les deux joueurs :
    // le joueur armé prend exactement ses coordonnées.
    await user.click(screen.getByRole("button", { name: "Paul I." }));

    await waitFor(() =>
      expect(placeTeamPlayer).toHaveBeenCalledWith(1, { team: "A", membership_id: 11, x_coord: 50, y_coord: 50 }),
    );
  });

  it("renvoie un joueur du terrain sur le banc depuis le menu de son pion", async () => {
    const user = userEvent.setup();
    vi.mocked(getSession).mockResolvedValue(
      makeSession({
        team_a: [
          makeTeamAssignment({ id: 1, membership_id: 10, is_on_field: true, x_coord: "30.00", y_coord: "40.00" }),
        ],
      }),
    );
    renderPage();
    await openEquipesTab(user);

    await user.click(await screen.findByRole("button", { name: "Paul I." }));
    await user.click(await screen.findByRole("button", { name: "Renvoyer sur le banc" }));

    await waitFor(() =>
      expect(placeTeamPlayer).toHaveBeenCalledWith(1, { team: "A", membership_id: 10, x_coord: null, y_coord: null }),
    );
  });

  it("affiche le message de l'API quand le plafond de 11 joueurs sur le terrain est atteint", async () => {
    const user = userEvent.setup();
    vi.mocked(placeTeamPlayer).mockRejectedValue(
      new ApiError(400, {
        detail:
          "Cette équipe compte déjà 11 joueurs sur le terrain : déposez ce joueur sur un coéquipier pour échanger les places, ou renvoyez-en un au banc d'abord.",
      }),
    );
    vi.mocked(getSession).mockResolvedValue(
      makeSession({
        team_a: [
          makeTeamAssignment({ id: 1, membership_id: 10, is_on_field: true, x_coord: "30.00", y_coord: "40.00" }),
        ],
      }),
    );
    renderPage();
    await openEquipesTab(user);

    await user.click(await screen.findByRole("button", { name: "Paul I." }));
    await user.click(await screen.findByRole("button", { name: "Renvoyer sur le banc" }));

    expect(await screen.findByText(/compte déjà 11 joueurs sur le terrain/)).toBeInTheDocument();
  });

  it("affiche le message d'inéligibilité renvoyé par l'API, sans le reformuler", async () => {
    const user = userEvent.setup();
    vi.mocked(placeTeamPlayer).mockRejectedValue(new ApiError(400, { detail: "En dette : 20 $.", code: "player_not_eligible" }));
    vi.mocked(getSession).mockResolvedValue(
      makeSession({
        team_a: [
          makeTeamAssignment({ id: 1, membership_id: 10, is_on_field: true, x_coord: "30.00", y_coord: "40.00" }),
          makeTeamAssignment({
            id: 2,
            membership_id: 11,
            player: { membership_id: 11, name: "Marc Tshibangu", jersey_number: 4, position: "defender", position_label: "Défenseur", photo: null },
            is_on_field: false,
          }),
        ],
      }),
    );
    renderPage();
    await openEquipesTab(user);

    await user.click(await screen.findByRole("button", { name: "Marc T." }));
    await user.click(await screen.findByRole("button", { name: "Placer sur le terrain" }));
    await user.click(screen.getByRole("button", { name: "Paul I." }));

    expect(await screen.findByText("En dette : 20 $.")).toBeInTheDocument();
  });

  it("n'affiche aucun joueur sur le banc quand tout le monde est sur le terrain", async () => {
    const user = userEvent.setup();
    vi.mocked(getSession).mockResolvedValue(
      makeSession({
        team_a: [makeTeamAssignment({ id: 1, membership_id: 10, is_on_field: true, x_coord: "30.00", y_coord: "40.00" })],
      }),
    );
    renderPage();
    await openEquipesTab(user);

    expect(await screen.findAllByText("Aucun joueur sur le banc.")).toHaveLength(2);
  });
});
