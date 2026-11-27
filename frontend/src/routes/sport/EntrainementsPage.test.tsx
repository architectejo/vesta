import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MyProfile } from "../../api/clubs";
import { ApiError } from "../../api/client";
import type {
  AttendanceRanking,
  AttendanceRankingEntry,
  MembershipBrief,
  MyAttendance,
  SessionHistoryResult,
  SessionStatsHistory,
} from "../../api/sport";
import { ToastProvider } from "../../design-system";
import { EntrainementsPage } from "./EntrainementsPage";

vi.mock("../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../api/clubs")>("../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});
vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return {
    ...actual,
    getSessionStatsHistory: vi.fn(),
    getAttendanceRanking: vi.fn(),
    getMyAttendance: vi.fn(),
    getSessionStats: vi.fn(),
  };
});
vi.mock("../../api/performance", async () => {
  const actual = await vi.importActual<typeof import("../../api/performance")>("../../api/performance");
  return { ...actual, listPerformanceTests: vi.fn(), getMyPerformanceOverview: vi.fn() };
});
import { getMyPerformanceOverview, listPerformanceTests } from "../../api/performance";
import { getMyProfile } from "../../api/clubs";
import { getAttendanceRanking, getMyAttendance, getSessionStats, getSessionStatsHistory } from "../../api/sport";

function profile(...roles: string[]): MyProfile {
  return {
    membership_id: 1,
    club: { id: 1, slug: "demo", name: "Club Test", logo: null, primary_color: "", secondary_color: "" },
    identity: { first_name: "A", last_name: "B", photo: null, email: "", phone: "", birth_date: null, weight_kg: null, height_cm: null },
    position: "midfielder",
    position_label: "Milieu",
    position_detail: "",
    jersey_number: null,
    membership_status: "active",
    membership_status_label: "Inscrit",
    roles: roles.map((role) => ({ role, label: role })),
    email_notifications_enabled: true,
  } as MyProfile;
}

function session(id: number, date: string, overrides: Partial<SessionHistoryResult> = {}): SessionHistoryResult {
  return {
    session_id: id,
    date,
    location: "Terrain A",
    expected: 10,
    present: 7,
    attendance_rate: 70,
    average_rating: null,
    my_rating: null,
    locked: false,
    ...overrides,
  };
}

function history(results: SessionHistoryResult[], overrides: Partial<SessionStatsHistory> = {}): SessionStatsHistory {
  return {
    period: "last10",
    season: { id: 1, label: "2026-2027" },
    average_attendance_rate: 72,
    average_rating: null,
    my_average_rating: null,
    results,
    ...overrides,
  };
}

function brief(id: number, name: string): MembershipBrief {
  return { membership_id: id, name, jersey_number: id, position: "", position_label: "", photo: null };
}

function entry(id: number, rate: number): AttendanceRankingEntry {
  return { player: brief(id, `Joueur ${id}`), sessions: 10, attended: rate / 10, present: rate / 10, late: 0, excused: 0, absent: 10 - rate / 10, rate };
}

function ranking(n: number): AttendanceRanking {
  const results = Array.from({ length: n }, (_, i) => entry(i + 1, 100 - i * 5));
  return { period: "last10", sessions_count: 10, late_counts_as_absent: true, results };
}

const SESSIONS = [session(1, "2026-11-01"), session(2, "2026-11-08", { attendance_rate: 80, present: 8 })];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>
          <EntrainementsPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  vi.mocked(getMyProfile).mockReset();
  vi.mocked(getSessionStatsHistory).mockReset();
  vi.mocked(getAttendanceRanking).mockReset();
  vi.mocked(getMyAttendance).mockReset();
  vi.mocked(getSessionStats).mockReset();
  vi.mocked(listPerformanceTests).mockReset();
  vi.mocked(listPerformanceTests).mockResolvedValue({ results: [] });
  vi.mocked(getMyPerformanceOverview).mockReset();
  vi.mocked(getMyPerformanceOverview).mockResolvedValue({
    membership: { membership_id: 1, name: "A B", jersey_number: null, position: "", position_label: "", photo: null },
    tests: [],
  });
  consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
});

describe("EntrainementsPage — staff", () => {
  beforeEach(() => {
    vi.mocked(getMyProfile).mockResolvedValue(profile("coach"));
    vi.mocked(getSessionStatsHistory).mockResolvedValue(
      history(SESSIONS.map((s) => ({ ...s, average_rating: "6.8" })), { average_rating: "6.8" }),
    );
    vi.mocked(getAttendanceRanking).mockResolvedValue(ranking(12));
  });

  it("affiche contexte du club, courbes, note moyenne et action de création", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Entraînements" })).toBeInTheDocument();
    expect(await screen.findByText("Club Test · Saison 2026-2027")).toBeInTheDocument();
    expect(await screen.findByText("Dernière séance : 80 %")).toBeInTheDocument();
    expect(screen.getByText("Note moyenne des séances")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Créer une séance" })).toBeInTheDocument();
    expect(getSessionStatsHistory).toHaveBeenCalledWith("last10");
  });

  it("change de période et recharge l'historique", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Dernière séance : 80 %");
    await user.click(screen.getByRole("button", { name: "Saison" }));
    await waitFor(() => expect(getSessionStatsHistory).toHaveBeenCalledWith("season"));
    await waitFor(() => expect(getAttendanceRanking).toHaveBeenCalledWith("season"));
  });

  it("assiduité : 5 meilleurs, 5 moins bons, puis liste complète paginée en modale", async () => {
    const user = userEvent.setup();
    renderPage();
    const section = await screen.findByRole("region", { name: "Assiduité" });
    expect(await within(section).findByText("Les plus assidus")).toBeInTheDocument();
    expect(within(section).getByText("Les moins assidus")).toBeInTheDocument();
    expect(within(section).getByText("Joueur 1")).toBeInTheDocument();
    expect(within(section).getByText("Joueur 12")).toBeInTheDocument();
    expect(within(section).queryByText("Joueur 6")).not.toBeInTheDocument();
    await user.click(within(section).getByRole("button", { name: "Voir tout" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Assiduité des joueurs")).toBeInTheDocument();
    expect(within(dialog).getByText("Joueur 6")).toBeInTheDocument();
  });

  it("clic sur une séance de la liste : modale avec les statistiques et lien vers la séance", async () => {
    const user = userEvent.setup();
    vi.mocked(getSessionStats).mockRejectedValue(new ApiError(500, {}));
    renderPage();
    const list = await screen.findByRole("region", { name: "Séances" });
    await user.click(within(list).getAllByRole("button")[0]!);
    const dialog = await screen.findByRole("dialog");
    expect(getSessionStats).toHaveBeenCalledWith(2);
    expect(within(dialog).getByRole("button", { name: "Ouvrir la séance" })).toBeInTheDocument();
  });

  it("liste des séances : 5 dernières puis « Voir plus »", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 8 }, (_, i) => session(i + 1, `2026-10-${String(i + 10)}`));
    vi.mocked(getSessionStatsHistory).mockResolvedValue(history(many));
    renderPage();
    const list = await screen.findByRole("region", { name: "Séances" });
    expect(within(list).getAllByRole("button", { name: /Terrain A/ })).toHaveLength(5);
    await user.click(within(list).getByRole("button", { name: "Voir plus" }));
    expect(within(list).getAllByRole("button", { name: /Terrain A/ })).toHaveLength(8);
  });
});

describe("EntrainementsPage — joueur", () => {
  beforeEach(() => {
    vi.mocked(getMyProfile).mockResolvedValue(profile());
    vi.mocked(getSessionStatsHistory).mockResolvedValue(
      history(
        SESSIONS.map((s) => ({ ...s, my_rating: "7.0" })),
        { my_average_rating: "7.0" },
      ),
    );
  });

  it("ne demande jamais le classement ; affiche « Mes notes » et « Mon assiduité »", async () => {
    const me: MyAttendance = { period: "last10", sessions_count: 10, sessions: 10, attended: 8, present: 8, late: 0, excused: 0, absent: 2, rate: 80, late_counts_as_absent: true };
    vi.mocked(getMyAttendance).mockResolvedValue(me);
    renderPage();
    expect(await screen.findByText("Mes notes")).toBeInTheDocument();
    expect(screen.queryByText("Note moyenne des séances")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Créer une séance" })).not.toBeInTheDocument();
    const mine = await screen.findByRole("region", { name: "Mon assiduité" });
    expect(await within(mine).findByText(/Vous avez participé à 8 séances sur 10/)).toBeInTheDocument();
    expect(getAttendanceRanking).not.toHaveBeenCalled();
    expect(screen.queryByText("Les plus assidus")).not.toBeInTheDocument();
  });

  it("compte sans fiche joueur (404) : message, pas d'erreur", async () => {
    vi.mocked(getMyAttendance).mockRejectedValue(new ApiError(404, { detail: "Aucune fiche." }));
    renderPage();
    expect(await screen.findByText("Aucune fiche joueur n'est associée à votre compte.")).toBeInTheDocument();
  });
});

describe("EntrainementsPage — refus et états", () => {
  it("403 du classement : bascule sur « Mon assiduité » sans rien montrer de nominatif", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profile("vice_president"));
    vi.mocked(getSessionStatsHistory).mockResolvedValue(history(SESSIONS));
    vi.mocked(getAttendanceRanking).mockRejectedValue(new ApiError(403, {}));
    vi.mocked(getMyAttendance).mockResolvedValue({
      period: "last10", sessions_count: 10, sessions: 10, attended: 5, present: 5, late: 0, excused: 0, absent: 5, rate: 50, late_counts_as_absent: true,
    });
    renderPage();
    expect(await screen.findByRole("region", { name: "Mon assiduité" })).toBeInTheDocument();
    expect(screen.queryByText("Les plus assidus")).not.toBeInTheDocument();
  });

  it("aucune séance : états vides, jamais de « 0 % »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profile("coach"));
    vi.mocked(getSessionStatsHistory).mockResolvedValue(history([], { average_attendance_rate: null }));
    vi.mocked(getAttendanceRanking).mockResolvedValue({ ...ranking(0) });
    renderPage();
    expect((await screen.findAllByText("Aucune séance pour l'instant.")).length).toBeGreaterThan(0);
    expect(screen.queryByText("0 %")).not.toBeInTheDocument();
  });

  it("une seule séance : message « au moins 2 séances »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profile("coach"));
    vi.mocked(getSessionStatsHistory).mockResolvedValue(history([SESSIONS[0]!]));
    vi.mocked(getAttendanceRanking).mockResolvedValue(ranking(1));
    renderPage();
    expect((await screen.findAllByText("Il faut au moins 2 séances pour afficher une évolution.")).length).toBeGreaterThan(0);
  });

  it("séance sans pointage dans la liste : « Non pointée », taux null jamais « 0 % »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profile("coach"));
    vi.mocked(getSessionStatsHistory).mockResolvedValue(
      history([session(1, "2026-11-01", { attendance_rate: null, present: 0 }), session(2, "2026-11-08")]),
    );
    vi.mocked(getAttendanceRanking).mockResolvedValue(ranking(2));
    renderPage();
    const list = await screen.findByRole("region", { name: "Séances" });
    expect(within(list).getByText("Non pointée")).toBeInTheDocument();
    expect(screen.queryByText(/\b0 %/)).not.toBeInTheDocument();
  });

  it("erreur de l'historique : message et « Réessayer »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profile("coach"));
    vi.mocked(getSessionStatsHistory).mockRejectedValue(new ApiError(500, {}));
    vi.mocked(getAttendanceRanking).mockResolvedValue(ranking(2));
    renderPage();
    expect(await screen.findByText("Impossible de charger les séances.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Réessayer/ }).length).toBeGreaterThan(0);
  });
});

describe("EntrainementsPage — tests de performance", () => {
  beforeEach(() => {
    vi.mocked(getSessionStatsHistory).mockResolvedValue(history(SESSIONS));
    vi.mocked(getAttendanceRanking).mockResolvedValue(ranking(3));
    vi.mocked(getMyAttendance).mockResolvedValue({ period: "last10", sessions: 10, attended: 8, rate: 80 } as MyAttendance);
  });

  it("Coach : carte « Tests de performance » avec « Nouveau test »", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profile("coach"));
    renderPage();
    const card = await screen.findByRole("region", { name: "Tests de performance" });
    expect(await within(card).findByText("Aucun test de performance pour l'instant.")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Nouveau test" })).toBeInTheDocument();
  });

  it("Président : lecture seule, aucun bouton de création", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profile("president"));
    renderPage();
    const card = await screen.findByRole("region", { name: "Tests de performance" });
    await within(card).findByText("Aucun test de performance pour l'instant.");
    expect(within(card).queryByRole("button", { name: "Nouveau test" })).not.toBeInTheDocument();
  });

  it("joueur ou Capitaine : « Mes tests » sans appel au catalogue du club", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profile("captain"));
    renderPage();
    const card = await screen.findByRole("region", { name: "Mes tests" });
    expect(await within(card).findByText("Vous n'avez pas encore de mesure.")).toBeInTheDocument();
    expect(listPerformanceTests).not.toHaveBeenCalled();
  });
});
