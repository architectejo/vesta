import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import type { SessionDetail, TeamAssignmentItem } from "../../api/sport";
import { ToastProvider } from "../../design-system";
import { VestiairePage } from "./VestiairePage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, getLockerRoom: vi.fn(), assignTeam: vi.fn(), setTeamFormation: vi.fn(), placeTeamPlayer: vi.fn() };
});

import { getMyProfile } from "../../api/clubs";
import { assignTeam, getLockerRoom, placeTeamPlayer, setTeamFormation } from "../../api/sport";

function makeProfile(...roles: string[]): MyProfile {
  return {
    membership_id: 1,
    club: { id: 1, slug: "test", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    identity: {
      first_name: "Jean",
      last_name: "Membre",
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

/** Restaure `matchMedia` par défaut (aucune query ne correspond) après
 * chaque test qui le personnalise (jsdom, même pattern que
 * `PlanDetailModal.test.tsx`). */
function mockMatchMedia(matching: string[]): void {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: matching.includes(query),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

/** Séance avec une équipe A : un joueur réellement placé sur le terrain
 * (coordonnées API) et un joueur sur le banc (`is_on_field: false`, sans
 * coordonnées exploitables) — mêmes formes que `serialize_team_assignment`
 * côté API (vérifié dans `apps/sport/serializers.py`). */
function makeSessionWithTeams(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return {
    id: 10,
    kind: "session",
    event_date: "2026-10-01",
    season_id: null,
    is_locked: false,
    unlocked_by: null,
    unlocked_at: null,
    unlock_reason: "",
    gathering_time: "07:30:00",
    late_arrival_cutoff: "08:00:00",
    location: "Terrain principal",
    team_a_color: "#2563eb",
    team_b_color: "#dc2626",
    team_a_formation: "",
    team_b_formation: "",
    instructions: "",
    late_arrival_counts_absent: true,
    counts: { present: 2, late: 0, excused: 0, not_marked: 0 },
    attendances: [],
    team_a: [
      {
        id: 1,
        membership_id: 101,
        player: {
          membership_id: 101,
          name: "Jean Kalala",
          jersey_number: 7,
          position: "forward",
          position_label: "Attaquant",
          photo: null,
        },
        team: "A",
        arrival_order: 1,
        is_on_field: true,
        x_coord: "30.50",
        y_coord: "72.00",
      },
      {
        id: 2,
        membership_id: 102,
        player: {
          membership_id: 102,
          name: "Paul Mbuyi",
          jersey_number: 4,
          position: "defender",
          position_label: "Défenseur",
          photo: null,
        },
        team: "A",
        arrival_order: 2,
        is_on_field: false,
        x_coord: null,
        y_coord: null,
      },
    ],
    team_b: [],
    unassigned: { to_place_manually: [], cannot_play: [] },
    ...overrides,
  };
}

function makeTeamAssignment(overrides: Partial<TeamAssignmentItem> = {}): TeamAssignmentItem {
  return {
    id: 1,
    membership_id: 101,
    player: { membership_id: 101, name: "Jean Kalala", jersey_number: 7, position: "forward", position_label: "Attaquant", photo: null },
    team: "A",
    arrival_order: 1,
    is_on_field: true,
    x_coord: "30.50",
    y_coord: "72.00",
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter>
          <VestiairePage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("VestiairePage", () => {
  beforeEach(() => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile());
  });

  afterEach(() => {
    vi.clearAllMocks();
    mockMatchMedia([]);
  });

  it("affiche l'état vide quand aucun événement n'a lieu aujourd'hui", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({ session: null, match: null, my_situation: null });
    renderPage();
    expect(await screen.findByText("Aucune séance ni aucun match aujourd'hui.")).toBeInTheDocument();
  });

  it("vue Terrain : place le pion à la vraie position renvoyée par l'API, pas sur une grille décorative", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Terrain" }));

    const pin = await screen.findByRole("button", { name: "Jean K." });
    // x_coord=30.50, y_coord=72.00, terrain vertical par défaut (sy = 100 - y).
    expect(pin.style.left).toBe("30.5%");
    expect(pin.style.top).toBe("28%");
  });

  it("vue Terrain : un joueur sur le banc n'est pas placé sur le terrain mais listé dans « Banc »", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Terrain" }));

    await screen.findByRole("button", { name: "Jean K." });
    expect(screen.getByText("Banc (1)")).toBeInTheDocument();
    expect(screen.getByText(/Paul Mbuyi/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Paul M." })).not.toBeInTheDocument();
  });

  it("vue Terrain : un toucher sur un pion ouvre une info-bulle avec nom complet, numéro et poste", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Terrain" }));
    const pin = await screen.findByRole("button", { name: "Jean K." });
    fireEvent.pointerDown(pin);
    fireEvent.pointerUp(pin);

    expect(await screen.findByText("Jean Kalala")).toBeInTheDocument();
    expect(screen.getByText("n° 7 · Attaquant")).toBeInTheDocument();
  });

  it("vue Terrain, rôle non autorisé (joueur simple) : aucun sélecteur de formation, le terrain reste en lecture seule", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Terrain" }));
    await screen.findByRole("button", { name: "Jean K." });

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Mode éditable du terrain (Coach, Capitaine, Président) — extension client
// du 30/09/2026, qui s'écarte sciemment de docs/ecrans/sport-vestiaire.md
// §3 point 3 (page de consultation pure) : voir le compte rendu de cette
// tâche.
// ---------------------------------------------------------------------------

describe("VestiairePage — mode éditable du terrain (Coach)", () => {
  beforeEach(() => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(assignTeam).mockResolvedValue(makeTeamAssignment());
    vi.mocked(setTeamFormation).mockResolvedValue(makeSessionWithTeams());
    vi.mocked(placeTeamPlayer).mockResolvedValue(makeSessionWithTeams());
  });

  afterEach(() => {
    vi.clearAllMocks();
    mockMatchMedia([]);
  });

  async function openTerrain(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: "Terrain" }));
  }

  it("choisit la formation de l'équipe A indépendamment de l'équipe B", async () => {
    const user = userEvent.setup();
    vi.mocked(getLockerRoom).mockResolvedValue({
      session: makeSessionWithTeams({ team_b_formation: "4-3-3" }),
      match: null,
      my_situation: null,
    });
    renderPage();
    await openTerrain(user);

    const selects = await screen.findAllByRole("combobox");
    expect(selects).toHaveLength(2);
    expect((selects[1] as HTMLSelectElement).value).toBe("4-3-3");

    await user.selectOptions(selects[0] as HTMLSelectElement, "4-3-3");

    expect(setTeamFormation).toHaveBeenCalledWith(10, { team: "A", formation: "4-3-3" });
  });

  it("place un joueur du banc sur le terrain en l'échangeant avec un coéquipier déjà placé (toucher)", async () => {
    const user = userEvent.setup();
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null });
    renderPage();
    await openTerrain(user);

    // Banc : toucher le joueur l'arme, puis « Placer sur le terrain ».
    await user.click(await screen.findByRole("button", { name: "Paul M." }));
    await user.click(await screen.findByRole("button", { name: "Placer sur le terrain" }));
    expect(await screen.findByText(/Touchez un emplacement libre/)).toBeInTheDocument();

    // Toucher le coéquipier déjà sur le terrain échange les deux joueurs.
    await user.click(screen.getByRole("button", { name: "Jean K." }));

    expect(placeTeamPlayer).toHaveBeenCalledWith(10, { team: "A", membership_id: 102, x_coord: 30.5, y_coord: 72 });
  });

  it("déplace un joueur du banc de l'équipe A vers le banc de l'équipe B via le menu « Passer en B »", async () => {
    const user = userEvent.setup();
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null });
    renderPage();
    await openTerrain(user);

    await user.click(await screen.findByRole("button", { name: "Paul M." }));
    await user.click(await screen.findByRole("button", { name: "Passer en B" }));

    expect(assignTeam).toHaveBeenCalledWith(10, { membership_id: 102, team: "B" });
  });

  it("affiche le système choisi et le nombre de postes pourvus au-dessus du sélecteur de formation", async () => {
    const user = userEvent.setup();
    vi.mocked(getLockerRoom).mockResolvedValue({
      session: makeSessionWithTeams({ team_a_formation: "4-3-3" }),
      match: null,
      my_situation: null,
    });
    renderPage();
    await openTerrain(user);

    expect(await screen.findByText("Système : 4-3-3")).toBeInTheDocument();
    expect(screen.getByText("1/11 postes pourvus")).toBeInTheDocument();
  });

  it("filtre le banc par nom/numéro et par poste quand il compte plusieurs joueurs", async () => {
    const user = userEvent.setup();
    vi.mocked(getLockerRoom).mockResolvedValue({
      session: makeSessionWithTeams({
        team_a: [
          ...makeSessionWithTeams().team_a,
          {
            id: 3,
            membership_id: 103,
            player: {
              membership_id: 103,
              name: "Marc Tshibangu",
              jersey_number: 11,
              position: "goalkeeper",
              position_label: "Gardien",
              photo: null,
            },
            team: "A",
            arrival_order: 3,
            is_on_field: false,
            x_coord: null,
            y_coord: null,
          },
        ],
      }),
      match: null,
      my_situation: null,
    });
    renderPage();
    await openTerrain(user);

    expect(await screen.findByRole("button", { name: "Paul M." })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Marc T." })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "GB" }));
    expect(screen.queryByRole("button", { name: "Paul M." })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Marc T." })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "GB" }));
    const search = screen.getByRole("textbox", { name: "Rechercher sur le banc de l'équipe A" });
    await user.type(search, "Paul");
    expect(screen.getByRole("button", { name: "Paul M." })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Marc T." })).not.toBeInTheDocument();
  });

  it("le terrain tient sans défilement vertical sur un écran d'ordinateur (largeur plafonnée à partir de 768 px)", async () => {
    const user = userEvent.setup();
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null });

    mockMatchMedia(["(min-width: 768px)"]);
    renderPage();
    await openTerrain(user);

    const board = await screen.findByRole("group", { name: "Équipe A" });
    expect(board.parentElement?.style.maxWidth).toMatch(/calc\(/);
  });

  it("ne plafonne pas la largeur du terrain sous 768 px (mobile)", async () => {
    const user = userEvent.setup();
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null });

    mockMatchMedia([]);
    renderPage();
    await openTerrain(user);

    const board = await screen.findByRole("group", { name: "Équipe A" });
    expect(board.parentElement?.style.maxWidth).toBe("");
  });
});
