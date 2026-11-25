import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ClubPlayerListItem, MyProfile } from "../../api/clubs";
import { ApiError } from "../../api/client";
import type { AttendanceCapabilities, BulkAttendanceResponse, SessionDetail } from "../../api/sport";
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
    bulkMarkAttendance: vi.fn(),
    listEventIncidents: vi.fn(),
    listEventEvaluations: vi.fn(),
  };
});

import { bulkMarkAttendance, getSession, listEventEvaluations, listEventIncidents } from "../../api/sport";
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

const ROSTER = [player(10, "Paul", "Ilunga"), player(11, "Anne", "Kasa"), player(12, "Marc", "Zola")];

const FULL: AttendanceCapabilities = { can_bulk_mark: true, can_bulk_excuse: true, can_set_arrival_time: true };

function makeSession(capabilities: AttendanceCapabilities | undefined, overrides: Partial<SessionDetail> = {}): SessionDetail {
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
    counts: { present: 1, late: 0, excused: 0, not_marked: 2 },
    // Marc est déjà pointé.
    attendances: [
      {
        id: 5,
        membership_id: 12,
        player: { membership_id: 12, name: "Marc Zola", jersey_number: 12, position: "midfielder", position_label: "Milieu", photo: null },
        status: "present",
        status_label: "Présent",
        arrived_at: "2026-09-27T06:30:00Z",
        excused_reason: "",
        marked_by: null,
        client_uuid: null,
      },
    ],
    team_a: [],
    team_b: [],
    unassigned: { to_place_manually: [], cannot_play: [] },
    capabilities,
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

async function openSelection(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("tab", { name: "Pointage" }));
  await user.click(await screen.findByRole("button", { name: "Sélectionner" }));
}

function response(overrides: Partial<BulkAttendanceResponse> = {}): BulkAttendanceResponse {
  return {
    batch_id: "b1",
    results: [
      { membership_id: 11, outcome: "created", message: "", attendance: null },
      { membership_id: 10, outcome: "created", message: "", attendance: null },
    ],
    counts: { created: 2, skipped: 0, refused: 0 },
    ...overrides,
  };
}

describe("SeancePage — pointage groupé", () => {
  beforeEach(() => {
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("coach"));
    vi.mocked(listClubPlayers).mockResolvedValue(ROSTER);
    vi.mocked(getSession).mockResolvedValue(makeSession(FULL));
    vi.mocked(listEventIncidents).mockResolvedValue({ count: 0, next_offset: null, results: [] });
    vi.mocked(listEventEvaluations).mockResolvedValue({ results: [], averages: {}, is_locked: false, locks_at: "" });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("masque « Sélectionner » sans capacité ou quand l'API la retire (séance verrouillée)", async () => {
    const user = userEvent.setup();
    vi.mocked(getSession).mockResolvedValue(makeSession({ can_bulk_mark: false, can_bulk_excuse: false, can_set_arrival_time: false }));
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Pointage" }));
    expect(await screen.findByText("Paul Ilunga")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sélectionner" })).not.toBeInTheDocument();
  });

  it("masque « Sélectionner » quand la réponse ne contient aucune capacité", async () => {
    const user = userEvent.setup();
    vi.mocked(getSession).mockResolvedValue(makeSession(undefined));
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Pointage" }));
    expect(await screen.findByText("Paul Ilunga")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sélectionner" })).not.toBeInTheDocument();
  });

  it("coche un joueur, Tout cocher (pointables seulement) puis Tout décocher", async () => {
    const user = userEvent.setup();
    renderPage();
    await openSelection(user);

    expect(screen.getByText("0 sélectionné")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pointer l'arrivée (0)" })).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: "Sélectionner Paul Ilunga" }));
    expect(screen.getByText("1 sélectionné")).toBeInTheDocument();

    // Marc, déjà pointé, n'est jamais cochable même avec le filtre « Tous ».
    await user.click(screen.getByRole("button", { name: "Tous" }));
    expect(screen.queryByRole("checkbox", { name: "Sélectionner Marc Zola" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Tout cocher (2)" }));
    expect(screen.getByText("2 sélectionnés")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Tout décocher" })[0]!);
    expect(screen.getByText("0 sélectionné")).toBeInTheDocument();
  });

  it("n'affiche « Absent excusé » et l'heure commune que si l'API les autorise (Capitaine)", async () => {
    const user = userEvent.setup();
    vi.mocked(getMyProfile).mockResolvedValue(makeProfile("captain"));
    vi.mocked(getSession).mockResolvedValue(
      makeSession({ can_bulk_mark: true, can_bulk_excuse: false, can_set_arrival_time: false }),
    );
    renderPage();
    await openSelection(user);
    expect(screen.queryByRole("button", { name: "Absent excusé" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Sélectionner Paul Ilunga" }));
    await user.click(screen.getByRole("button", { name: "Pointer l'arrivée (1)" }));
    expect(await screen.findByText("Pointer 1 joueur ?")).toBeInTheDocument();
    expect(screen.queryByText("Indiquer une autre heure d'arrivée")).not.toBeInTheDocument();
  });

  it("exige une confirmation, puis envoie le corps exact (rangs dans l'ordre de sélection, client_uuid)", async () => {
    const user = userEvent.setup();
    vi.mocked(bulkMarkAttendance).mockResolvedValue(response());
    renderPage();
    await openSelection(user);

    await user.click(screen.getByRole("checkbox", { name: "Sélectionner Anne Kasa" }));
    await user.click(screen.getByRole("checkbox", { name: "Sélectionner Paul Ilunga" }));
    await user.click(screen.getByRole("button", { name: "Pointer l'arrivée (2)" }));

    expect(await screen.findByText("Pointer 2 joueurs ?")).toBeInTheDocument();
    expect(screen.getByText("Un pointage ne peut pas être retiré ensuite.")).toBeInTheDocument();
    expect(bulkMarkAttendance).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Pointer (2)" }));

    await waitFor(() => expect(bulkMarkAttendance).toHaveBeenCalledTimes(1));
    const [kind, eventId, body] = vi.mocked(bulkMarkAttendance).mock.calls[0]!;
    expect(kind).toBe("session");
    expect(eventId).toBe(1);
    expect(body.action).toBe("arrive");
    expect(body.arrived_at).toBeUndefined();
    expect(body.items).toEqual([
      {
        membership_id: 11,
        client_uuid: expect.stringMatching(/^[0-9a-f-]{36}$/),
        client_recorded_at: expect.any(String),
        selection_rank: 1,
      },
      {
        membership_id: 10,
        client_uuid: expect.stringMatching(/^[0-9a-f-]{36}$/),
        client_recorded_at: expect.any(String),
        selection_rank: 2,
      },
    ]);
    expect(body.items[0]!.client_uuid).not.toBe(body.items[1]!.client_uuid);
    expect(await screen.findByText(/2 joueurs pointés à/)).toBeInTheDocument();
    // Succès complet : on sort du mode sélection.
    expect(screen.queryByRole("button", { name: "Terminer" })).not.toBeInTheDocument();
  });

  it("n'envoie rien si on annule la confirmation", async () => {
    const user = userEvent.setup();
    renderPage();
    await openSelection(user);
    await user.click(screen.getByRole("checkbox", { name: "Sélectionner Paul Ilunga" }));
    await user.click(screen.getByRole("button", { name: "Pointer l'arrivée (1)" }));
    await user.click(await screen.findByRole("button", { name: "Annuler" }));
    expect(bulkMarkAttendance).not.toHaveBeenCalled();
  });

  it("envoie l'heure commune saisie par le Coach (arrived_at)", async () => {
    const user = userEvent.setup();
    vi.mocked(bulkMarkAttendance).mockResolvedValue(response());
    renderPage();
    await openSelection(user);
    await user.click(screen.getByRole("checkbox", { name: "Sélectionner Paul Ilunga" }));
    await user.click(screen.getByRole("button", { name: "Pointer l'arrivée (1)" }));
    await user.click(await screen.findByRole("checkbox", { name: "Indiquer une autre heure d'arrivée" }));
    const timeInput = screen.getByLabelText(/Heure d'arrivée commune/);
    await user.clear(timeInput);
    await user.type(timeInput, "07:15");
    await user.click(screen.getByRole("button", { name: "Pointer (1)" }));

    await waitFor(() => expect(bulkMarkAttendance).toHaveBeenCalled());
    const body = vi.mocked(bulkMarkAttendance).mock.calls[0]![2];
    expect(body.arrived_at).toBe(new Date("2026-09-27T07:15:00").toISOString());
  });

  it("affiche le succès partiel avec les refus et ne garde cochés que les refusés", async () => {
    const user = userEvent.setup();
    vi.mocked(bulkMarkAttendance).mockResolvedValue({
      batch_id: "b2",
      results: [
        { membership_id: 11, outcome: "created", message: "", attendance: null },
        { membership_id: 10, outcome: "refused", message: "Ce joueur n'est plus inscrit.", attendance: null },
      ],
      counts: { created: 1, skipped: 0, refused: 1 },
    });
    renderPage();
    await openSelection(user);
    await user.click(screen.getByRole("button", { name: "Tout cocher (2)" }));
    await user.click(screen.getByRole("button", { name: "Pointer l'arrivée (2)" }));
    await user.click(await screen.findByRole("button", { name: "Pointer (2)" }));

    const dialog = await screen.findByRole("dialog", { name: "Résultat du pointage groupé" });
    expect(within(dialog).getByText("1 pointé, 1 refusé")).toBeInTheDocument();
    expect(within(dialog).getByText("Paul Ilunga")).toBeInTheDocument();
    expect(within(dialog).getByText("Ce joueur n'est plus inscrit.")).toBeInTheDocument();

    await user.click(within(dialog).getByText("Fermer"));
    await waitFor(() => expect(screen.getByText("1 sélectionné")).toBeInTheDocument());
    expect(screen.getByRole("checkbox", { name: "Sélectionner Paul Ilunga" })).toBeChecked();
  });

  it("explique clairement un verrouillage de minuit (409 event_locked)", async () => {
    const user = userEvent.setup();
    vi.mocked(bulkMarkAttendance).mockRejectedValue(
      new ApiError(409, { detail: "Cette séance est verrouillée.", code: "event_locked" }),
    );
    renderPage();
    await openSelection(user);
    await user.click(screen.getByRole("checkbox", { name: "Sélectionner Paul Ilunga" }));
    await user.click(screen.getByRole("button", { name: "Pointer l'arrivée (1)" }));
    await user.click(await screen.findByRole("button", { name: "Pointer (1)" }));

    expect(await screen.findByText("La séance vient d'être verrouillée. Rien n'a été enregistré.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Terminer" })).not.toBeInTheDocument();
  });

  it("absences excusées : motif obligatoire, corps exact, mêmes client_uuid à l'essai suivant", async () => {
    const user = userEvent.setup();
    vi.mocked(bulkMarkAttendance)
      .mockRejectedValueOnce(new ApiError(0, null))
      .mockResolvedValueOnce(response());
    renderPage();
    await openSelection(user);
    await user.click(screen.getByRole("button", { name: "Tout cocher (2)" }));
    await user.click(screen.getByRole("button", { name: "Absent excusé" }));

    await user.click(await screen.findByRole("button", { name: "Marquer excusés (2)" }));
    expect(await screen.findByText("Choisissez un motif.")).toBeInTheDocument();
    expect(bulkMarkAttendance).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Voyage" }));
    await user.type(screen.getByLabelText(/Précision/), "Déplacement");
    await user.click(screen.getByRole("button", { name: "Marquer excusés (2)" }));

    // Coupure réseau : message, la modale reste ouverte, rien n'est perdu.
    expect(await screen.findByText(/hors connexion/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Marquer excusés (2)" }));
    await waitFor(() => expect(bulkMarkAttendance).toHaveBeenCalledTimes(2));

    const first = vi.mocked(bulkMarkAttendance).mock.calls[0]![2];
    const second = vi.mocked(bulkMarkAttendance).mock.calls[1]![2];
    expect(first.action).toBe("excuse");
    expect(first.reason_code).toBe("travel");
    expect(first.reason_detail).toBe("Déplacement");
    expect(second.items.map((i) => i.client_uuid)).toEqual(first.items.map((i) => i.client_uuid));
  });
});
