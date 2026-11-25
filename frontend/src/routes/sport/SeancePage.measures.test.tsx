import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import type { SessionDetail, SessionStats } from "../../api/sport";
import { ToastProvider } from "../../design-system";
import { SeancePage } from "./SeancePage";

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

describe("Séance › Bilan — mesures", () => {
  it("Coach (can_measure) : « Mesurer » ouvre l'écran de mesure plein écran", async () => {
    const user = userEvent.setup();
    vi.mocked(getMyProfile).mockResolvedValue(profile("coach"));
    vi.mocked(getSessionStats).mockResolvedValue(stats(true));
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Bilan" }));
    await user.click(await screen.findByRole("button", { name: "Mesurer" }));
    const dialog = await screen.findByRole("dialog", { name: "Mesurer" });
    expect(await within(dialog).findByText("Aucun test de performance pour l'instant.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Commencer" })).toBeInTheDocument();
  });

  it("Capitaine (can_measure faux) : carte visible, aucun bouton « Mesurer »", async () => {
    const user = userEvent.setup();
    vi.mocked(getMyProfile).mockResolvedValue(profile("captain"));
    vi.mocked(getSessionStats).mockResolvedValue(stats(false));
    renderPage();
    await user.click(await screen.findByRole("tab", { name: "Bilan" }));
    const card = await screen.findByRole("region", { name: "Mesures de la séance" });
    expect(within(card).getByText("Aucune mesure pendant cette séance.")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Mesurer" })).not.toBeInTheDocument();
  });
});
