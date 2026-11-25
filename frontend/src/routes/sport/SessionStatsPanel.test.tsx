import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { MembershipBrief, SessionEvaluationStats, SessionStats } from "../../api/sport";
import { SessionStatsPanel } from "./SessionStatsPanel";

vi.mock("../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../api/sport")>("../../api/sport");
  return { ...actual, getSessionStats: vi.fn() };
});
import { getSessionStats } from "../../api/sport";

function brief(id: number, name: string): MembershipBrief {
  return { membership_id: id, name, jersey_number: id, position: "midfielder", position_label: "Milieu", photo: null };
}

function makeEvaluations(overrides: Partial<SessionEvaluationStats> = {}): SessionEvaluationStats {
  return {
    average: "6.8",
    evaluated: 3,
    eligible: 5,
    remaining: 2,
    delta_vs_average: "0.4",
    ranking_available: true,
    best: [
      { rank: 1, player: brief(1, "Alice Best"), note: "8.5" },
      { rank: 2, player: brief(2, "Bob Second"), note: "7.0" },
    ],
    lowest: [{ rank: 1, player: brief(3, "Carl Low"), note: "4.5" }],
    distribution: [
      { label: "0 à 2", min: "0", max: "2", count: 0 },
      { label: "2 à 4", min: "2", max: "4", count: 0 },
      { label: "4 à 6", min: "4", max: "6", count: 1 },
      { label: "6 à 8", min: "6", max: "8", count: 1 },
      { label: "8 à 10", min: "8", max: "10", count: 1 },
    ],
    players: [
      {
        player: brief(1, "Alice Best"),
        overall: "8.5",
        technical: "9",
        physical: null,
        tactical: "8",
        mental: "8",
        attitude: "9",
        evaluators_count: 2,
        comments: [{ text: "Très bon match", visible_to_player: true }],
      },
      {
        player: brief(3, "Carl Low"),
        overall: "4.5",
        technical: "4",
        physical: "5",
        tactical: null,
        mental: null,
        attitude: null,
        evaluators_count: 1,
        comments: [{ text: "Doit progresser", visible_to_player: false }],
      },
    ],
    not_evaluated: [brief(9, "Dan Pending")],
    open_until: "2026-11-10T12:00:00Z",
    locked: false,
    hours_left: 31,
    ...overrides,
  };
}

function makeStats(overrides: Partial<SessionStats> = {}): SessionStats {
  return {
    session_id: 7,
    date: "2026-11-08",
    generated_at: "2026-11-08T10:30:00Z",
    attendance: {
      expected: 10,
      present: 6,
      late: 1,
      absent: 2,
      excused: 1,
      rate: 60,
      nobody_marked: false,
      late_counts_as_absent: true,
      late_label: "En retard, compté absent",
      late_family: "danger",
      delta_vs_average: -4,
      late_list: [{ ...brief(21, "Léa Retard"), arrived_at: "2026-11-08T08:20:00Z" }],
      excused_list: [{ ...brief(22, "Eli Excusé"), reason: "Voyage" }],
      absent_list: [brief(23, "Abe Absent"), brief(24, "Ada Absent")],
    },
    evaluations: makeEvaluations(),
    my_evaluation: null,
    measures: [],
    capabilities: { can_evaluate: true, can_measure: false },
    ...overrides,
  };
}

function renderPanel(onEvaluate?: () => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SessionStatsPanel sessionId={7} onEvaluate={onEvaluate} />
    </QueryClientProvider>,
  );
}

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  vi.mocked(getSessionStats).mockReset();
  consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
});

describe("SessionStatsPanel — présence", () => {
  it("affiche compteurs, taux, écart et libellé du retard servis par l'API", async () => {
    vi.mocked(getSessionStats).mockResolvedValue(makeStats());
    renderPanel();
    const card = await screen.findByRole("region", { name: "Présence" });
    expect(within(card).getAllByText("60 %").length).toBeGreaterThan(0);
    expect(within(card).getByText("10 joueurs attendus")).toBeInTheDocument();
    expect(within(card).getAllByText("En retard, compté absent").length).toBeGreaterThan(0);
    expect(within(card).getByText("−4 pts")).toBeInTheDocument();
  });

  it("masque l'écart quand l'API ne le fournit pas", async () => {
    const stats = makeStats();
    stats.attendance.delta_vs_average = null;
    vi.mocked(getSessionStats).mockResolvedValue(stats);
    renderPanel();
    const card = await screen.findByRole("region", { name: "Présence" });
    expect(within(card).queryByText("Écart avec la moyenne")).not.toBeInTheDocument();
  });

  it("séance sans pointage : taux « — », jamais « 0 % », message dédié", async () => {
    const stats = makeStats();
    stats.attendance = {
      ...stats.attendance,
      present: 0,
      late: 0,
      excused: 0,
      absent: 10,
      rate: null,
      nobody_marked: true,
      delta_vs_average: null,
      late_list: [],
      excused_list: [],
    };
    vi.mocked(getSessionStats).mockResolvedValue(stats);
    renderPanel();
    const card = await screen.findByRole("region", { name: "Présence" });
    expect(within(card).getByText("Personne n'est encore pointé.")).toBeInTheDocument();
    expect(within(card).getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("0 %")).not.toBeInTheDocument();
  });

  it("déplie la liste des retards au clic sur la tuile, avec l'heure d'arrivée", async () => {
    const user = userEvent.setup();
    vi.mocked(getSessionStats).mockResolvedValue(makeStats());
    renderPanel();
    const card = await screen.findByRole("region", { name: "Présence" });
    expect(within(card).queryByText("Léa Retard")).not.toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: /En retard, compté absent/ }));
    expect(within(card).getByText("Léa Retard")).toBeInTheDocument();
  });

  it("limite les listes à 5 lignes puis « Voir plus »", async () => {
    const user = userEvent.setup();
    const stats = makeStats();
    stats.attendance.absent_list = Array.from({ length: 7 }, (_, i) => brief(100 + i, `Absent ${i + 1}`));
    stats.attendance.absent = 7;
    vi.mocked(getSessionStats).mockResolvedValue(stats);
    renderPanel();
    const card = await screen.findByRole("region", { name: "Présence" });
    await user.click(within(card).getByRole("button", { name: /^Absents \(7\)/ }));
    expect(within(card).queryByText("Absent 6")).not.toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Voir plus" }));
    expect(within(card).getByText("Absent 7")).toBeInTheDocument();
  });
});

describe("SessionStatsPanel — Notes du Coach", () => {
  it("affiche moyenne, évalués sur pointés, meilleures et plus faibles notes", async () => {
    vi.mocked(getSessionStats).mockResolvedValue(makeStats());
    renderPanel();
    const card = await screen.findByRole("region", { name: "Notes du Coach" });
    expect(within(card).getByText("6,8 sur 10")).toBeInTheDocument();
    expect(within(card).getByText("Évaluations ouvertes encore 31 h")).toBeInTheDocument();
    expect(within(card).getByText("Alice Best")).toBeInTheDocument();
    expect(within(card).getByText("8,5")).toBeInTheDocument();
    expect(within(card).getByText("Notes les plus faibles")).toBeInTheDocument();
    expect(within(card).getByText("Carl Low")).toBeInTheDocument();
    expect(within(card).getByText("+0,4")).toBeInTheDocument();
  });

  it("moins de 2 joueurs évalués : message à la place du classement", async () => {
    vi.mocked(getSessionStats).mockResolvedValue(
      makeStats({ evaluations: makeEvaluations({ ranking_available: false, best: [], lowest: [], evaluated: 1 }) }),
    );
    renderPanel();
    const card = await screen.findByRole("region", { name: "Notes du Coach" });
    expect(within(card).getByText("Pas assez de notes pour un classement.")).toBeInTheDocument();
    expect(within(card).queryByText("Meilleures notes")).not.toBeInTheDocument();
  });

  it("aucune note : message d'état vide ; verrouillée : message des 48 h", async () => {
    vi.mocked(getSessionStats).mockResolvedValue(
      makeStats({
        evaluations: makeEvaluations({
          evaluated: 0,
          average: null,
          best: [],
          lowest: [],
          players: [],
          not_evaluated: [],
          remaining: 0,
          locked: true,
          hours_left: null,
          ranking_available: false,
        }),
      }),
    );
    renderPanel();
    const card = await screen.findByRole("region", { name: "Notes du Coach" });
    expect(within(card).getByText("Aucune note n'a été saisie dans les 48 heures.")).toBeInTheDocument();
    expect(within(card).getByText(/Évaluations verrouillées depuis le/)).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Évaluer les joueurs" })).not.toBeInTheDocument();
  });

  it("« Évaluer les joueurs » : proposé si l'API l'autorise et s'il reste des joueurs, sinon absent", async () => {
    const user = userEvent.setup();
    const onEvaluate = vi.fn();
    vi.mocked(getSessionStats).mockResolvedValue(makeStats());
    const view = renderPanel(onEvaluate);
    await user.click(await screen.findByRole("button", { name: "Évaluer les joueurs" }));
    expect(onEvaluate).toHaveBeenCalledOnce();
    view.unmount();

    vi.mocked(getSessionStats).mockResolvedValue(makeStats({ capabilities: { can_evaluate: false, can_measure: false } }));
    renderPanel(onEvaluate);
    await screen.findByRole("region", { name: "Notes du Coach" });
    expect(screen.queryByRole("button", { name: "Évaluer les joueurs" })).not.toBeInTheDocument();
  });

  it("répartition en 5 tranches dépliable", async () => {
    const user = userEvent.setup();
    vi.mocked(getSessionStats).mockResolvedValue(makeStats());
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Voir la répartition" }));
    expect(screen.getByRole("figure", { name: "Répartition des notes" })).toBeInTheDocument();
  });

  it("modale de détail : critères par joueur, « — » si non renseigné, commentaires et visibilité", async () => {
    const user = userEvent.setup();
    vi.mocked(getSessionStats).mockResolvedValue(makeStats());
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Voir toutes les notes" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/3 joueurs évalués sur 5 · moyenne 6,8 sur 10/)).toBeInTheDocument();
    expect(within(dialog).getByText("Pas encore évalués (1)")).toBeInTheDocument();
    expect(within(dialog).getByText("Dan Pending")).toBeInTheDocument();
    expect(within(dialog).getAllByText("—").length).toBeGreaterThan(0);
    await user.click(within(dialog).getAllByRole("button", { name: "Voir" })[0]!);
    expect(await screen.findByText("Visible par le joueur")).toBeInTheDocument();
  });
});

describe("SessionStatsPanel — vue du joueur", () => {
  it("evaluations null : aucun bloc staff, seulement « Ma note » avec ses critères et commentaires visibles", async () => {
    vi.mocked(getSessionStats).mockResolvedValue(
      makeStats({
        evaluations: null,
        my_evaluation: {
          overall: "7.0",
          criteria: { technical: "7", physical: "6", tactical: null, mental: null, attitude: null },
          comments: ["Bien joué"],
        },
      }),
    );
    renderPanel();
    const card = await screen.findByRole("region", { name: "Ma note" });
    expect(within(card).getByText("7,0")).toBeInTheDocument();
    expect(within(card).getByText("Technique 7 · Physique 6")).toBeInTheDocument();
    expect(within(card).getByText("Bien joué")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Notes du Coach" })).not.toBeInTheDocument();
    expect(screen.queryByText("Meilleures notes")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Voir toutes les notes" })).not.toBeInTheDocument();
  });

  it("joueur non évalué : message dédié", async () => {
    vi.mocked(getSessionStats).mockResolvedValue(makeStats({ evaluations: null, my_evaluation: null }));
    renderPanel();
    expect(await screen.findByText("Vous n'avez pas encore été évalué pour cette séance.")).toBeInTheDocument();
  });
});

describe("SessionStatsPanel — états", () => {
  it("erreur : message et « Réessayer »", async () => {
    const user = userEvent.setup();
    vi.mocked(getSessionStats).mockRejectedValueOnce(new ApiError(500, {}));
    renderPanel();
    expect(await screen.findByText("Impossible de charger les statistiques.")).toBeInTheDocument();
    vi.mocked(getSessionStats).mockResolvedValue(makeStats());
    await user.click(screen.getByRole("button", { name: "Réessayer" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Présence" })).toBeInTheDocument());
  });
});
