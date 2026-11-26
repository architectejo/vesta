import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BoardDashboard } from "../../../api/clubBoardDashboard";
import { ApiError } from "../../../api/client";
import { ThemeProvider, ToastProvider, currentMonth, shiftMonth } from "../../../design-system";
import { BoardDashboardPage } from "./BoardDashboardPage";

vi.mock("../../../api/clubBoardDashboard", async () => {
  const actual = await vi.importActual<typeof import("../../../api/clubBoardDashboard")>(
    "../../../api/clubBoardDashboard",
  );
  return { ...actual, getBoardDashboard: vi.fn(), getBoardSection: vi.fn() };
});

vi.mock("../../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../../api/clubs")>("../../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});

import { getBoardDashboard, getBoardSection } from "../../../api/clubBoardDashboard";
import { getMyProfile } from "../../../api/clubs";

const PERIOD = {
  mode: "month" as const,
  month: "2026-11",
  season_id: null,
  label: "novembre 2026",
  start: "2026-11-01",
  end: "2026-11-30",
  months: ["2026-09", "2026-10", "2026-11"],
};

function dashboard(overrides: Partial<BoardDashboard> = {}): BoardDashboard {
  return {
    period: PERIOD,
    currency: "USD",
    as_of: "2026-11-15",
    attendance: {
      events_count: 4,
      average_rate: "74.00",
      last_rate: "72.00",
      late_counts_absent: false,
      totals: { expected: 40, present: 30, late: 0, excused: 4, absent: 6 },
      by_kind: {},
      points: [
        { event_id: 1, kind: "session", kind_label: "Séance", date: "2026-11-03", expected: 10, present: 8, late: 0, excused: 1, absent: 1, rate: "80.00" },
        { event_id: 2, kind: "session", kind_label: "Séance", date: "2026-11-10", expected: 10, present: 7, late: 0, excused: 1, absent: 2, rate: "70.00" },
      ],
      series: [],
    },
    contributions: {
      collected: "1240.00",
      collected_mandatory: "1200.00",
      collected_free: "40.00",
      due_total: "1500.00",
      matured_due_total: "1500.00",
      matured_due_covered: "1230.00",
      collection_rate: "82.00",
      series: [
        { month: "2026-10", label: "octobre 2026", collected: "900.00", matured_due_total: "1000.00", matured_due_covered: "900.00", collection_rate: "90.00" },
        { month: "2026-11", label: "novembre 2026", collected: "1240.00", matured_due_total: "1500.00", matured_due_covered: "1230.00", collection_rate: "82.00" },
      ],
    },
    squad_status: {
      as_of: "2026-11-15",
      total: 33,
      in_good_standing: { count: 24, rate: "72.73" },
      in_debt: { count: 6, rate: "18.18", amount: "120.00" },
      pending: { count: 2, rate: "6.06" },
      suspended: { count: 1, rate: "3.03", also_in_debt_count: 0, also_in_debt_amount: "0.00" },
    },
    cash: {
      collected: "1240.00",
      spent: "380.00",
      net: "860.00",
      available_cash: "860.00",
      series: [{ month: "2026-11", label: "novembre 2026", collected: "1240.00", spent: "380.00" }],
    },
    expenses_by_category: {
      total_spent: "380.00",
      categories: [{ category_id: 3, name: "Transport", amount: "380.00", count: 2 }],
      pending_count: 1,
      pending_amount: "40.00",
      unjustified_count: 1,
      release_blocked: true,
      release_blocked_reason: "Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée.",
    },
    upcoming_finance: {
      as_of: "2026-11-15",
      until: "2026-12-15",
      count: 1,
      items: [{ kind: "contribution_due", date: "2026-11-20", label: "Échéance « Mensuelle 10 »", amount: "60.00", players_count: 6 }],
    },
    newcomers: {
      arrivals_count: 3,
      departures_count: 1,
      avatars: [{ membership_id: 5, player_name: "Aimé Mukendi", photo: null }],
      pending_count: 2,
      series: [{ month: "2026-11", label: "novembre 2026", arrivals: 3, departures: 1 }],
    },
    results: {
      played: 12,
      wins: 7,
      draws: 2,
      losses: 3,
      goals_for: 24,
      goals_against: 15,
      form: [
        { match_id: 1, date: "2026-11-08", opponent: "FC Lemba", venue: "home", venue_label: "Domicile", match_type: "friendly", match_type_label: "Amical", goals_for: 3, goals_against: 1, result: "V", result_label: "Victoire" },
      ],
    },
    discipline: {
      yellow_cards: 11,
      red_cards: 1,
      internal_sanctions: 0,
      suspended_count: 2,
      series: [{ month: "2026-11", label: "novembre 2026", yellow: 11, red: 1, internal: 0 }],
    },
    squad_trend: {
      current_count: 33,
      window_start: "2025-12-01",
      window_end: "2026-11-15",
      arrivals_count: 3,
      departures_count: 1,
      series: [{ month: "2026-11", label: "novembre 2026", count: 33, arrivals: 3, departures: 1 }],
    },
    fitness: {
      total: 33,
      fit: 30,
      fit_with_restriction: 1,
      unfit: 2,
      recorded_count: 33,
      no_information: false,
      unfit_players: [{ membership_id: 9, player_name: "Patrick Ilunga", photo: null, fitness_status: "unfit", return_date: "2026-12-01" }],
      notice: "Le détail médical n'est visible que par le Médecin et le joueur.",
    },
    upcoming: {
      as_of: "2026-11-15",
      until: "2026-12-15",
      count: 1,
      items: [{ kind: "match", date: "2026-11-22", time: "15:00:00", label: "Match contre AS Ngaba", detail: "Stade du Cinquantenaire" }],
    },
    attendance_ranking: {
      players_count: 2,
      top: [{ membership_id: 1, player_name: "Joseph Kasa", photo: null, expected: 4, present: 4, late: 0, excused: 0, absent: 0, rate: "100.00" }],
      bottom: [{ membership_id: 2, player_name: "Marc Tshibola", photo: null, expected: 4, present: 1, late: 0, excused: 0, absent: 3, rate: "25.00" }],
    },
    to_process: { counts: { expenses_to_validate: 1, assistance_requests: 0, minutes_to_sign: 1, blocked_applications: 0 }, total: 2 },
    equipment_out: { lines_count: 0, articles_count: 0, overdue_count: 0, items: [] },
    coach_notes: { average: "7.40", evaluations: 20, events_count: 4, points: [], series: [{ month: "2026-11", label: "novembre 2026", average: "7.40" }] },
    feed_activity: {
      posts_count: 12,
      comments_count: 20,
      likes_count: 40,
      granularity: "week",
      series: [{ start: "2026-11-02", label: "Semaine du 02/11", posts: 12 }],
    },
    ...overrides,
  };
}

function renderPage(initialEntry = "/tableau-de-bord") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider initialTheme="light">
        <ToastProvider>
          <MemoryRouter initialEntries={[initialEntry]}>
            <BoardDashboardPage />
          </MemoryRouter>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function matchesPage(offset: number, count: number) {
  const items = Array.from({ length: count }, (_, i) => ({
    match_id: offset + i + 1,
    date: "2026-11-08",
    opponent: `Adversaire ${offset + i + 1}`,
    venue: "home",
    venue_label: "Domicile",
    match_type: "friendly",
    match_type_label: "Amical",
    goals_for: 2,
    goals_against: 1,
    result: "V" as const,
    result_label: "Victoire",
  }));
  return items;
}

beforeEach(() => {
  vi.mocked(getBoardDashboard).mockReset();
  vi.mocked(getBoardSection).mockReset();
  vi.mocked(getMyProfile).mockReset();
  vi.mocked(getMyProfile).mockResolvedValue({ club: { name: "Club Test" } } as never);
});

describe("BoardDashboardPage", () => {
  it("affiche les cartes avec les données de l'API, la devise du club et le nom du club", async () => {
    vi.mocked(getBoardDashboard).mockResolvedValue(dashboard());
    renderPage();

    expect(await screen.findByRole("heading", { name: "Tableau de bord du club" })).toBeInTheDocument();
    expect(screen.getByText(/74\s%\sde présence moyenne/)).toBeInTheDocument();
    expect(screen.getByText(/82\s%\srecouvré/)).toBeInTheDocument();
    expect(screen.getByText(/^1\s240 USD encaissés$/)).toBeInTheDocument();
    expect(screen.getByText(/Caisse disponible : 860 USD/)).toBeInTheDocument();
    expect(screen.getByText("7 V · 2 N · 3 D")).toBeInTheDocument();
    expect(screen.getByText(/En dette : 120 USD au total/)).toBeInTheDocument();
    expect(screen.getByText(/Club Test/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir l'accueil" })).toHaveAttribute("href", "/");
    // Ordre P1 -> P3 de la fiche.
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles.slice(0, 4)).toEqual(["Présences", "Cotisations", "Situation de l'effectif", "Caisse : encaissements et dépenses"]);
    expect(getBoardDashboard).toHaveBeenCalledWith(null);
  });

  it("isole une carte en erreur et la relance avec « Réessayer »", async () => {
    vi.mocked(getBoardDashboard).mockResolvedValue(
      dashboard({ attendance: { error: "Impossible de charger les présences." } }),
    );
    renderPage();

    expect(await screen.findByText("Impossible de charger les présences.")).toBeInTheDocument();
    // Les autres cartes restent affichées.
    expect(screen.getByText(/82\s%\srecouvré/)).toBeInTheDocument();
    const callsBefore = vi.mocked(getBoardDashboard).mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    await waitFor(() => expect(vi.mocked(getBoardDashboard).mock.calls.length).toBeGreaterThan(callsBefore));
  });

  it("affiche le message réservé quand l'API répond 403", async () => {
    vi.mocked(getBoardDashboard).mockRejectedValue(new ApiError(403, { detail: "Interdit." }));
    renderPage();

    expect(
      await screen.findByText("Cette page est réservée au Président et au Vice-président."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Retour à l'accueil" })).toBeInTheDocument();
  });

  it("propose « Réessayer » quand toute la page échoue", async () => {
    vi.mocked(getBoardDashboard).mockRejectedValue(new ApiError(500, {}));
    renderPage();
    expect(await screen.findByText("Impossible de charger le tableau de bord.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });

  it("affiche un état vide explicite par carte", async () => {
    vi.mocked(getBoardDashboard).mockResolvedValue(
      dashboard({
        attendance: { ...dashboard().attendance, events_count: 0, points: [] } as BoardDashboard["attendance"],
        results: { played: 0, wins: 0, draws: 0, losses: 0, goals_for: 0, goals_against: 0, form: [] },
        fitness: { ...(dashboard().fitness as object), no_information: true } as BoardDashboard["fitness"],
        equipment_out: { lines_count: 0, articles_count: 0, overdue_count: 0, items: [] },
        newcomers: { arrivals_count: 0, departures_count: 0, avatars: [], pending_count: 0, series: [] },
      }),
    );
    renderPage();

    expect(await screen.findByText("Aucune séance sur la période.")).toBeInTheDocument();
    expect(screen.getByText("Aucun match joué sur la période.")).toBeInTheDocument();
    expect(screen.getByText("Aucune information d'aptitude enregistrée.")).toBeInTheDocument();
    expect(screen.getByText("Aucun matériel à retourner.")).toBeInTheDocument();
    expect(screen.getByText("Aucun nouveau joueur ce mois-ci.")).toBeInTheDocument();
  });

  it("change de période : flèche « mois précédent » -> nouvelle requête et mémorisation dans l'URL", async () => {
    vi.mocked(getBoardDashboard).mockResolvedValue(dashboard());
    renderPage();
    await screen.findByRole("heading", { name: "Tableau de bord du club" });

    await userEvent.click(screen.getByRole("button", { name: "Mois précédent" }));
    const previous = shiftMonth(currentMonth(), -1);
    await waitFor(() =>
      expect(getBoardDashboard).toHaveBeenLastCalledWith({ mode: "month", month: previous }),
    );
  });

  it("lit la période dans l'URL (?mois=) et la saison courante (?saison=)", async () => {
    vi.mocked(getBoardDashboard).mockResolvedValue(dashboard());
    renderPage("/tableau-de-bord?mois=2026-09");
    await screen.findByRole("heading", { name: "Tableau de bord du club" });
    expect(getBoardDashboard).toHaveBeenCalledWith({ mode: "month", month: "2026-09" });
  });

  it("demande la saison courante sans identifiant", async () => {
    vi.mocked(getBoardDashboard).mockResolvedValue(
      dashboard({ period: { ...PERIOD, mode: "season", month: null, season_id: 3, label: "Saison 2026-2027" } }),
    );
    renderPage("/tableau-de-bord?saison=courante");
    await screen.findByRole("heading", { name: "Tableau de bord du club" });
    expect(getBoardDashboard).toHaveBeenCalledWith({ mode: "season", seasonId: null });
  });

  it("ouvre la modale de détail et charge « Voir plus » avec offset et only exacts", async () => {
    vi.mocked(getBoardDashboard).mockResolvedValue(dashboard());
    vi.mocked(getBoardSection)
      .mockResolvedValueOnce({
        section: "results",
        period: PERIOD,
        summary: dashboard().results,
        top_scorers: [{ membership_id: 1, player_name: "Joseph Kasa", photo: null, count: 6 }],
        top_assists: [],
        matches: { items: matchesPage(0, 5), count: 8, next_offset: 5 },
      } as never)
      .mockResolvedValueOnce({
        section: "results",
        period: PERIOD,
        matches: { items: matchesPage(5, 3), count: 8, next_offset: null },
      } as never);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Voir le détail : Résultats" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/Adversaire 1$/)).toBeInTheDocument();
    expect(vi.mocked(getBoardSection)).toHaveBeenCalledWith("results", null, { limit: 5 });
    expect(within(dialog).getByText("Joseph Kasa")).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("button", { name: "Voir plus" }));
    expect(await within(dialog).findByText(/Adversaire 8$/)).toBeInTheDocument();
    expect(vi.mocked(getBoardSection)).toHaveBeenLastCalledWith("results", null, {
      limit: 5,
      offset: 5,
      only: "matches",
    });
    // Plus de page suivante : le bouton disparaît.
    expect(within(dialog).queryByRole("button", { name: "Voir plus" })).not.toBeInTheDocument();
  });

  it("modale Aptitude : aptitude et date de retour, jamais de diagnostic", async () => {
    vi.mocked(getBoardDashboard).mockResolvedValue(dashboard());
    const player = { photo: null, return_date: "2026-12-01" };
    vi.mocked(getBoardSection).mockResolvedValue({
      section: "fitness",
      period: PERIOD,
      summary: dashboard().fitness,
      unfit: { items: [{ membership_id: 9, player_name: "Patrick Ilunga", fitness_status: "unfit", ...player }], count: 1, next_offset: null },
      restricted: { items: [], count: 0, next_offset: null },
      fit: { items: [], count: 0, next_offset: null },
    } as never);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Voir le détail : Aptitude de l'effectif" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/retour prévu le 01\/12\/2026/)).toBeInTheDocument();
    expect(within(dialog).getByText("Le détail médical n'est visible que par le Médecin et le joueur.")).toBeInTheDocument();

    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/diagnostic|blessure|pathologie|maladie|traitement/i);
    expect(within(dialog).queryByRole("link")).not.toBeInTheDocument();
  });

  it("affiche le bandeau rouge de la page quand une dépense non justifiée bloque les libérations (série 5, fiche §3)", async () => {
    vi.mocked(getBoardDashboard).mockResolvedValue(dashboard());
    renderPage();
    await screen.findByRole("heading", { name: "Tableau de bord du club" });
    expect(
      screen.getByText("Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée."),
    ).toBeInTheDocument();
  });

  it("n'affiche pas ce bandeau quand les libérations ne sont pas bloquées ou que la carte est en erreur", async () => {
    const base = dashboard();
    vi.mocked(getBoardDashboard).mockResolvedValue(
      dashboard({
        expenses_by_category: {
          ...(base.expenses_by_category as Exclude<BoardDashboard["expenses_by_category"], { error: string }>),
          release_blocked: false,
          release_blocked_reason: null,
        },
      }),
    );
    const { unmount } = renderPage();
    await screen.findByRole("heading", { name: "Tableau de bord du club" });
    expect(screen.queryByText(/aucune nouvelle dépense ne peut être libérée/)).not.toBeInTheDocument();
    unmount();

    vi.mocked(getBoardDashboard).mockResolvedValue(dashboard({ expenses_by_category: { error: "Impossible de charger les dépenses." } }));
    renderPage();
    await screen.findByRole("heading", { name: "Tableau de bord du club" });
    expect(screen.queryByText(/aucune nouvelle dépense ne peut être libérée/)).not.toBeInTheDocument();
  });

  it("carte Aptitude : un inapte sans date de retour l'indique au lieu de rester muet (série 5)", async () => {
    const base = dashboard();
    const fitness = base.fitness as Exclude<BoardDashboard["fitness"], { error: string }>;
    vi.mocked(getBoardDashboard).mockResolvedValue(
      dashboard({
        fitness: {
          ...fitness,
          unfit_players: [{ membership_id: 9, player_name: "Patrick Ilunga", photo: null, fitness_status: "unfit", return_date: null }],
        },
      }),
    );
    renderPage();
    expect(await screen.findByText("Patrick Ilunga · date de retour non précisée")).toBeInTheDocument();
  });

  it("aucun terme de diagnostic médical sur la page", async () => {
    vi.mocked(getBoardDashboard).mockResolvedValue(dashboard());
    renderPage();
    await screen.findByRole("heading", { name: "Tableau de bord du club" });
    expect(document.body.textContent ?? "").not.toMatch(/diagnostic|blessure|pathologie|maladie/i);
  });

  it("n'affiche pas la carte « Tests de performance » (non livrée)", async () => {
    vi.mocked(getBoardDashboard).mockResolvedValue(dashboard());
    renderPage();
    await screen.findByRole("heading", { name: "Tableau de bord du club" });
    expect(screen.queryByText(/Tests de performance/)).not.toBeInTheDocument();
  });
});
