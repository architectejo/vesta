import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
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
  return {
    ...actual,
    getLockerRoom: vi.fn(),
    assignTeam: vi.fn(),
    setTeamFormation: vi.fn(),
    placeTeamPlayer: vi.fn(),
    createSession: vi.fn(),
  };
});

import { getMyProfile } from "../../api/clubs";
import { assignTeam, createSession, getLockerRoom, placeTeamPlayer, setTeamFormation } from "../../api/sport";

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
    vi.mocked(getLockerRoom).mockResolvedValue({ session: null, match: null, my_situation: null, next_event: null });
    renderPage();
    expect(await screen.findByText("Aucune séance ni aucun match aujourd'hui.")).toBeInTheDocument();
    // Sans `next_event`, aucune précision n'est ajoutée (comportement
    // inchangé avant l'ajout du champ).
    expect(screen.queryByText(/Prochain rendez-vous/)).not.toBeInTheDocument();
  });

  it("précise le prochain rendez-vous (séance) quand rien n'a lieu aujourd'hui", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({
      session: null,
      match: null,
      my_situation: null,
      next_event: { type: "session", id: 99, event_date: "2026-10-04", gathering_time: "07:30:00", location: "" },
    });
    renderPage();
    expect(await screen.findByText("Aucune séance ni aucun match aujourd'hui.")).toBeInTheDocument();
    expect(await screen.findByText("Prochain rendez-vous : Séance · dimanche 4 octobre · 07:30")).toBeInTheDocument();
  });

  it("précise le prochain rendez-vous (match) quand rien n'a lieu aujourd'hui", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({
      session: null,
      match: null,
      my_situation: null,
      next_event: {
        type: "match",
        id: 77,
        event_date: "2026-10-09",
        kickoff_time: "15:00:00",
        opponent: "FC Exemple",
        location: "",
      },
    });
    renderPage();
    expect(
      await screen.findByText("Prochain rendez-vous : Match contre FC Exemple · vendredi 9 octobre · 15:00"),
    ).toBeInTheDocument();
  });

  it("n'affiche pas le bouton « Créer une séance » pour un simple joueur", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({ session: null, match: null, my_situation: null, next_event: null });
    renderPage();
    await screen.findByText("Aucune séance ni aucun match aujourd'hui.");
    expect(screen.queryByText("Créer une séance")).not.toBeInTheDocument();
  });

  it("vue Liste : « Prénom N. » jamais tronqué, ligne de 44 px, joueur connecté mis en avant avec « Vous » (§3 point 3, §7)", async () => {
    // Vérification visuelle B3 (360 px) : les noms complets étaient coupés
    // par des points de suspension (« Gérard Simu… ») et « Vous » manquait.
    vi.mocked(getLockerRoom).mockResolvedValue({
      session: makeSessionWithTeams(),
      match: null,
      my_situation: {
        attendance: { id: 9, membership_id: 102 } as unknown as SessionDetail["attendances"][number],
        team: "A",
        eligible: true,
        reason: "",
        reason_code: "",
      },
      next_event: null,
    });
    renderPage();

    const jean = (await screen.findByText("Jean K.")).closest("li")!;
    expect(jean).toHaveTextContent("7 Jean K.");
    expect(jean.innerHTML).not.toMatch(/\btruncate\b/);
    expect(jean.className).toMatch(/\bmin-h-11\b/);
    expect(jean).not.toHaveAttribute("aria-current");
    expect(screen.queryByText("Jean Kalala")).not.toBeInTheDocument();

    const me = screen.getByText("Paul M.").closest("li")!;
    expect(me).toHaveAttribute("aria-current", "true");
    expect(me).toHaveTextContent("Vous");
    expect(me.className).toMatch(/\bbg-surface-muted\b/);
  });

  it("vue Terrain : place le pion à la vraie position renvoyée par l'API, pas sur une grille décorative", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null, next_event: null });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Terrain" }));

    const pin = await screen.findByRole("button", { name: "Jean K." });
    // x_coord=30.50, y_coord=72.00, terrain vertical par défaut (sy = 100 - y).
    expect(pin.style.left).toBe("30.5%");
    expect(pin.style.top).toBe("28%");
  });

  it("vue Terrain : un joueur sur le banc n'est pas placé sur le terrain mais listé dans « Banc »", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null, next_event: null });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Terrain" }));

    await screen.findByRole("button", { name: "Jean K." });
    expect(screen.getByText("Banc (1)")).toBeInTheDocument();
    expect(screen.getByText(/Paul Mbuyi/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Paul M." })).not.toBeInTheDocument();
  });

  it("vue Terrain : un toucher sur un pion ouvre une info-bulle avec nom complet, numéro et poste", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null, next_event: null });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Terrain" }));
    const pin = await screen.findByRole("button", { name: "Jean K." });
    fireEvent.pointerDown(pin);
    fireEvent.pointerUp(pin);

    expect(await screen.findByText("Jean Kalala")).toBeInTheDocument();
    expect(screen.getByText("n° 7 · Attaquant")).toBeInTheDocument();
  });

  it("vue Terrain, rôle non autorisé (joueur simple) : aucun sélecteur de formation, le terrain reste en lecture seule", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null, next_event: null });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Terrain" }));
    await screen.findByRole("button", { name: "Jean K." });

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});

describe("VestiairePage — « Créer une séance » depuis l'état vide (Coach)", () => {
  beforeEach(() => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(getLockerRoom).mockResolvedValue({ session: null, match: null, my_situation: null, next_event: null });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("affiche le bouton « Créer une séance » pour le Coach quand rien n'a lieu aujourd'hui", async () => {
    renderPage();
    expect(await screen.findByText("Créer une séance")).toBeInTheDocument();
  });

  it("ouvre la modale de création et appelle createSession, puis rafraîchit le vestiaire", async () => {
    const user = userEvent.setup();
    const created = {
      id: 123,
      kind: "session" as const,
      event_date: "2026-10-12",
      season_id: null,
      is_locked: false,
      unlocked_by: null,
      unlocked_at: null,
      unlock_reason: "",
      gathering_time: "07:30:00",
      late_arrival_cutoff: "08:00:00",
      location: "Terrain municipal",
      team_a_color: "#1d4ed8",
      team_b_color: "#dc2626",
      team_a_formation: "" as const,
      team_b_formation: "" as const,
      instructions: "",
      late_arrival_counts_absent: true,
      counts: { present: 0, late: 0, excused: 0, not_marked: 0 },
      attendances: [],
      team_a: [],
      team_b: [],
      unassigned: { to_place_manually: [], cannot_play: [] },
    };
    vi.mocked(createSession).mockResolvedValue(created);
    renderPage();

    await user.click(await screen.findByText("Créer une séance"));
    expect(await screen.findByRole("heading", { name: "Créer une séance" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Rassemblement"), { target: { value: "07:30" } });
    fireEvent.change(screen.getByLabelText("Limite d'arrivée"), { target: { value: "08:00" } });

    await user.click(screen.getByRole("button", { name: "Créer la séance" }));

    expect(createSession).toHaveBeenCalledWith(
      expect.objectContaining({ gathering_time: "07:30", late_arrival_cutoff: "08:00" }),
    );
    expect(await screen.findByText("Séance créée. Les joueurs ont été prévenus.")).toBeInTheDocument();
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
      next_event: null,
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
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null, next_event: null });
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
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null, next_event: null });
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
      next_event: null,
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
      next_event: null,
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
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null, next_event: null });

    mockMatchMedia(["(min-width: 768px)"]);
    renderPage();
    await openTerrain(user);

    const board = await screen.findByRole("group", { name: "Équipe A" });
    expect(board.parentElement?.style.maxWidth).toMatch(/calc\(/);
  });

  it("ne plafonne pas la largeur du terrain sous 768 px (mobile)", async () => {
    const user = userEvent.setup();
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null, next_event: null });

    mockMatchMedia([]);
    renderPage();
    await openTerrain(user);

    const board = await screen.findByRole("group", { name: "Équipe A" });
    expect(board.parentElement?.style.maxWidth).toBe("");
  });
});

describe("VestiairePage - joueurs non jouables (sport-vestiaire.md §4.4)", () => {
  it("affiche un badge gris « Indisponible » sans motif, jamais « En attente »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("member"));
    vi.mocked(getLockerRoom).mockResolvedValue({
      session: makeSessionWithTeams({
        unassigned: {
          to_place_manually: [],
          cannot_play: [{ membership_id: 55, name: "Luc Tshala", photo: null }] as never,
        },
      }),
      match: null,
      my_situation: null,
      next_event: null,
    });
    renderPage();

    expect(await screen.findByText("Luc Tshala")).toBeInTheDocument();
    expect(screen.getByText("Indisponible")).toBeInTheDocument();
    expect(screen.queryByText("En attente")).not.toBeInTheDocument();
  });
});

describe("VestiairePage - présents sans équipe (sport-vestiaire.md §9.1)", () => {
  it("affiche des pions de 40 px, grisés avec cadenas pour les joueurs bloqués", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("member"));
    vi.mocked(getLockerRoom).mockResolvedValue({
      session: makeSessionWithTeams({
        unassigned: {
          to_place_manually: [{ membership_id: 54, name: "Anne Kasa", photo: null, jersey_number: 9, attendance_status: "present" }] as never,
          cannot_play: [{ membership_id: 55, name: "Luc Tshala", photo: null }] as never,
        },
      }),
      match: null,
      my_situation: null,
      next_event: null,
    });
    renderPage();
    expect(await screen.findByText("Luc Tshala")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Luc T. : indisponible" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anne K." })).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Série 5 (B2) : en-tête et rafraîchissement (sport-vestiaire.md §3 et §6)
  // -------------------------------------------------------------------------

  it("écrit la date de l'événement dans le contexte de l'en-tête (§3)", async () => {
    vi.mocked(getLockerRoom).mockResolvedValue({ session: makeSessionWithTeams(), match: null, my_situation: null, next_event: null });
    renderPage();
    expect(await screen.findByText("Club de test · jeudi 1 octobre")).toBeInTheDocument();
  });

  it("garde le vestiaire affiché quand un rafraîchissement échoue et propose « Réessayer » (§6)", async () => {
    vi.mocked(getLockerRoom).mockResolvedValueOnce({ session: makeSessionWithTeams(), match: null, my_situation: null, next_event: null });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter>
            <VestiairePage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Mis à jour à \d{2}:\d{2}/)).toBeInTheDocument();
    vi.mocked(getLockerRoom).mockRejectedValue(new Error("réseau"));
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ["sport", "locker-room"] });
    });
    expect(await screen.findByText(/Mise à jour impossible · \d{2}:\d{2}/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
    // La dernière version reçue reste affichée, sans page d'erreur.
    expect(screen.getByText("Vestiaire du jour")).toBeInTheDocument();
    expect(screen.queryByText("Impossible de charger le vestiaire.")).not.toBeInTheDocument();
  });

  it("affiche la page d'erreur seulement si aucun vestiaire n'a jamais été reçu", async () => {
    vi.mocked(getLockerRoom).mockRejectedValue(new Error("réseau"));
    renderPage();
    expect(await screen.findByText("Impossible de charger le vestiaire.")).toBeInTheDocument();
  });
});
