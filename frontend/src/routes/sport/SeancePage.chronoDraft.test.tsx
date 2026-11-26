import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import type { SessionDetail, SessionStats } from "../../api/sport";
import { ToastProvider } from "../../design-system";
import { SeancePage } from "./SeancePage";
import { setStoredIdentity } from "../../auth/session";
import { chronoDraftKey, type ChronoDraft } from "./performance/chronoDraft";
import { brief, makeTest } from "./performance/testFixtures";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn(), listClubPlayers: vi.fn() };
});
vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, getSession: vi.fn(), getSessionStats: vi.fn(), listEventIncidents: vi.fn(), listEventEvaluations: vi.fn() };
});
vi.mock("../../api/performance", async () => {
  const actual = await vi.importActual<typeof import("../../api/performance")>("../../api/performance");
  return { ...actual, listPerformanceTests: vi.fn(), listPerformanceTemplates: vi.fn(), bulkPerformanceResults: vi.fn() };
});
import { getMyProfile, listClubPlayers } from "../../api/clubs";
import { listPerformanceTemplates, listPerformanceTests } from "../../api/performance";
import { getSession, getSessionStats, listEventEvaluations, listEventIncidents } from "../../api/sport";

function profile(...roles: string[]): MyProfile {
  return {
    membership_id: 1,
    club: { id: 1, slug: "test", name: "Club de test", logo: null, primary_color: "", secondary_color: "" },
    roles: roles.map((role) => ({ role, label: role })),
  } as unknown as MyProfile;
}

function stats(canMeasure: boolean): SessionStats {
  return {
    session_id: 1,
    date: "2026-11-10",
    generated_at: "2026-11-10T10:00:00Z",
    attendance: {
      expected: 1,
      present: 1,
      late: 0,
      absent: 0,
      excused: 0,
      rate: 100,
      nobody_marked: false,
      late_counts_as_absent: true,
      late_label: "En retard",
      late_family: "danger",
      delta_vs_average: null,
      late_list: [],
      excused_list: [],
      absent_list: [],
    },
    evaluations: null,
    my_evaluation: null,
    measures: [],
    capabilities: { can_evaluate: false, can_measure: canMeasure },
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
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

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  window.localStorage.clear();
  vi.mocked(listClubPlayers).mockResolvedValue([]);
  vi.mocked(listEventIncidents).mockResolvedValue({ count: 0, next_offset: null, results: [] });
  vi.mocked(listEventEvaluations).mockResolvedValue({ results: [], averages: {}, is_locked: false, locks_at: "" });
  vi.mocked(listPerformanceTests).mockResolvedValue({ results: [] });
  vi.mocked(listPerformanceTemplates).mockResolvedValue({ results: [], health_help: "" });
  vi.mocked(getSession).mockResolvedValue({
    id: 1,
    kind: "session",
    event_date: "2026-11-10",
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
    counts: { present: 0, late: 0, excused: 0, not_marked: 0 },
    attendances: [],
    team_a: [],
    team_b: [],
    unassigned: { to_place_manually: [], cannot_play: [] },
  } as SessionDetail);
  consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
  vi.clearAllMocks();
});

const USER_ID = 42;

function identity(userId: number) {
  setStoredIdentity({
    user: {
      id: userId,
      email: "coach@example.org",
      first_name: "Coach",
      last_name: "Test",
      is_superuser: false,
      must_change_password: false,
      preferred_theme: "classic",
    },
    club: null,
  });
}

function storeDraft(overrides: Partial<ChronoDraft> = {}) {
  const savedAt = new Date("2026-11-10T09:32:00").getTime();
  const draft = {
    v: 1,
    userId: USER_ID,
    eventId: 1,
    testId: 1,
    testName: "Sprint 30 m",
    startMode: "group",
    playerIds: [1],
    step: "stopwatch",
    stopwatch: {
      phase: "finished",
      groupStart: savedAt - 5000,
      runners: { 1: { status: "stopped", startedAt: savedAt - 5000, timeMs: 5000 } },
      rounds: [],
      frozen: 5000,
    },
    savedAt,
    ...overrides,
  } as ChronoDraft;
  window.localStorage.setItem(chronoDraftKey(draft.userId, draft.eventId), JSON.stringify(draft));
}

describe("Séance — chrono non enregistré retrouvé", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-10T10:00:00") });
    vi.mocked(getMyProfile).mockResolvedValue(profile("coach"));
    vi.mocked(getSessionStats).mockResolvedValue(stats(true));
    vi.mocked(listPerformanceTests).mockResolvedValue({
      results: [{ ...makeTest(), last_measured_on: null, last_measured_count: 0, season_best: null }],
    });
    // Même séance que plus haut, avec Alice pointée (seuls les joueurs pointés sont mesurables).
    const base = vi.mocked(getSession).getMockImplementation();
    vi.mocked(getSession).mockImplementation(async (id) => ({
      ...(await base!(id)),
      attendances: [{ id: 1, membership_id: 1, player: brief(1, "Alice Durand"), status: "present" }],
    }) as unknown as SessionDetail);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("propose « Reprendre » : le chrono rouvre avec les temps déjà pris", async () => {
    const user = userEvent.setup();
    identity(USER_ID);
    storeDraft();
    renderPage();
    expect(await screen.findByText(/Un chrono non enregistré a été retrouvé \(Sprint 30 m, 09:32\)\./)).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Reprendre" }));
    const dialog = await screen.findByRole("dialog", { name: "Chronomètre : Sprint 30 m" });
    expect(await within(dialog).findByText("5,00 s")).toBeInTheDocument();
    expect(within(dialog).getByText("Chrono terminé")).toBeInTheDocument();
    expect(screen.queryByText(/Un chrono non enregistré a été retrouvé/)).not.toBeInTheDocument();
  });

  it("« Abandonner » demande confirmation puis efface la sauvegarde", async () => {
    const user = userEvent.setup();
    identity(USER_ID);
    storeDraft();
    renderPage();
    await screen.findByText(/Un chrono non enregistré a été retrouvé/);
    await user.click(screen.getByRole("button", { name: "Abandonner" }));
    const dialog = await screen.findByRole("dialog", { name: "Abandonner ces mesures ?" });
    await user.click(within(dialog).getByRole("button", { name: "Continuer" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Abandonner ces mesures ?" })).not.toBeInTheDocument());
    expect(screen.getByText(/Un chrono non enregistré a été retrouvé/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Abandonner" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Abandonner ces mesures ?" })).getByRole("button", { name: "Abandonner" }));
    expect(screen.queryByText(/Un chrono non enregistré a été retrouvé/)).not.toBeInTheDocument();
    expect(window.localStorage.getItem(chronoDraftKey(USER_ID, 1))).toBeNull();
  });

  it("n'est jamais proposé à un autre utilisateur du même téléphone", async () => {
    identity(7);
    storeDraft();
    renderPage();
    expect(await screen.findByRole("tab", { name: "Bilan" })).toBeInTheDocument();
    expect(screen.queryByText(/Un chrono non enregistré a été retrouvé/)).not.toBeInTheDocument();
    expect(window.localStorage.getItem(chronoDraftKey(USER_ID, 1))).not.toBeNull();
  });

  it("mesure plus permise (can_measure faux : rôle retiré ou fenêtre fermée) : seul « Abandonner » est proposé", async () => {
    vi.mocked(getSessionStats).mockResolvedValue(stats(false));
    identity(USER_ID);
    storeDraft();
    renderPage();
    await screen.findByText(/Un chrono non enregistré a été retrouvé/);
    await waitFor(() => expect(getSessionStats).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: "Abandonner" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reprendre" })).not.toBeInTheDocument();
  });

  it("efface à l'ouverture les sauvegardes trop anciennes d'autres séances", async () => {
    identity(USER_ID);
    storeDraft({ eventId: 9, savedAt: new Date("2026-11-07T09:00:00").getTime() });
    storeDraft();
    renderPage();
    await screen.findByText(/Un chrono non enregistré a été retrouvé/);
    expect(window.localStorage.getItem(chronoDraftKey(USER_ID, 9))).toBeNull();
    expect(window.localStorage.getItem(chronoDraftKey(USER_ID, 1))).not.toBeNull();
  });
});
