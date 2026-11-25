import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client";
import type { PerformanceEvolution, PerformanceLeaderboard, PerformanceTestOverview } from "../../../api/performance";
import { ToastProvider } from "../../../design-system";
import { PerformanceTestsCard } from "./PerformanceTestsCard";
import { brief, makeTest, makeValue } from "./testFixtures";

vi.mock("../../../api/performance", async () => {
  const actual = await vi.importActual<typeof import("../../../api/performance")>("../../../api/performance");
  return {
    ...actual,
    listPerformanceTests: vi.fn(),
    listPerformanceTemplates: vi.fn(),
    createPerformanceTest: vi.fn(),
    updatePerformanceTest: vi.fn(),
    archivePerformanceTest: vi.fn(),
    getPerformanceLeaderboard: vi.fn(),
    getMyPerformanceOverview: vi.fn(),
    getMyPerformanceEvolution: vi.fn(),
    getPlayerPerformanceEvolution: vi.fn(),
  };
});
import {
  archivePerformanceTest,
  createPerformanceTest,
  getMyPerformanceEvolution,
  getMyPerformanceOverview,
  getPerformanceLeaderboard,
  getPlayerPerformanceEvolution,
  listPerformanceTemplates,
  listPerformanceTests,
  updatePerformanceTest,
} from "../../../api/performance";

const HEALTH_HELP =
  "Les tests mesurent une performance sportive. N'y enregistrez aucune donnée de santé (poids, taille, fréquence cardiaque) : elles relèvent du Médecin.";

function overview(overrides: Partial<PerformanceTestOverview> = {}): PerformanceTestOverview {
  return {
    ...makeTest(),
    last_measured_on: "2026-11-10",
    last_measured_count: 14,
    season_best: { player: { membership_id: 1, name: "Alice Durand" }, ...makeValue({ time_ms: 4210, display: "4,21 s" }) },
    ...overrides,
  };
}

function leaderboard(): PerformanceLeaderboard {
  return {
    test: makeTest({ has_results: true }),
    period: "last",
    event: { id: 7, date: "2026-11-10" },
    results: [
      {
        rank: 1,
        player: brief(1, "Alice Durand"),
        result_id: 11,
        event_id: 7,
        date: "2026-11-10",
        measures_count: 2,
        trend: { direction: "progress", delta: "-120", delta_display: "0,12 s", text: "en progrès de 0,12 s" },
        personal_record: true,
        ...makeValue({ time_ms: 4210, display: "4,21 s" }),
      },
    ],
  };
}

function evolution(): PerformanceEvolution {
  return {
    membership: brief(1, "Alice Durand"),
    test: makeTest({ has_results: true }),
    best: { date: "2026-11-10", result_id: 11, ...makeValue({ time_ms: 4210, display: "4,21 s" }) },
    last: { date: "2026-11-10", result_id: 11, ...makeValue({ time_ms: 4210, display: "4,21 s" }) },
    progression: {
      direction: "progress",
      delta: "-310",
      delta_display: "0,31 s",
      text: "en progrès de 0,31 s depuis la première mesure",
      legend: "Plus bas = plus rapide",
    },
    points: [
      { event_id: 5, date: "2026-10-01", result_id: 5, sort_value: "4520", ...makeValue() },
      { event_id: 7, date: "2026-11-10", result_id: 11, sort_value: "4210", ...makeValue({ time_ms: 4210, display: "4,21 s" }) },
    ],
    results: [
      { id: 11, event_id: 7, date: "2026-11-10", attempt_no: 1, method: "stopwatch", method_label: "Chrono", personal_record: true, ...makeValue({ time_ms: 4210, display: "4,21 s" }) },
      { id: 5, event_id: 5, date: "2026-10-01", attempt_no: 1, method: "manual", method_label: "Saisie manuelle", personal_record: false, ...makeValue() },
    ],
  };
}

function renderCard(props: { staff: boolean; canManage: boolean }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <PerformanceTestsCard {...props} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  vi.mocked(listPerformanceTests).mockResolvedValue({ results: [overview()] });
  vi.mocked(listPerformanceTemplates).mockResolvedValue({
    results: [
      { code: "sprint_10", name: "Sprint 10 m", kind: "timed_distance", distance_m: "10", duration_s: null, attempts: null, time_limit_s: null, unit: "", decimals: 0, higher_is_better: true, description: "Départ arrêté." },
    ],
    health_help: HEALTH_HELP,
  });
  vi.mocked(getPerformanceLeaderboard).mockResolvedValue(leaderboard());
  vi.mocked(getPlayerPerformanceEvolution).mockResolvedValue(evolution());
  vi.mocked(getMyPerformanceEvolution).mockResolvedValue(evolution());
  vi.mocked(getMyPerformanceOverview).mockResolvedValue({
    membership: brief(1, "Alice Durand"),
    tests: [
      {
        test: makeTest({ has_results: true }),
        best: { date: "2026-10-01", ...makeValue() },
        last: { date: "2026-11-10", ...makeValue({ time_ms: 4600, display: "4,60 s" }) },
        results_count: 2,
      },
    ],
  });
  consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
  vi.clearAllMocks();
});

describe("PerformanceTestsCard — rôles", () => {
  it("Coach / Assistant : catalogue du club et bouton « Nouveau test »", async () => {
    renderCard({ staff: true, canManage: true });
    const card = await screen.findByRole("region", { name: "Tests de performance" });
    expect(await within(card).findByText("Sprint 30 m")).toBeInTheDocument();
    expect(within(card).getByText("Chrono sur 30 m")).toBeInTheDocument();
    expect(within(card).getByText("Dernière mesure le 10 novembre 2026 · 14 joueurs")).toBeInTheDocument();
    expect(within(card).getByText("Meilleur de la saison : 4,21 s · Alice Durand")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Nouveau test" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Tests archivés" })).toBeInTheDocument();
  });

  it("Président / VP / DS : lecture seule, aucun bouton de création", async () => {
    renderCard({ staff: true, canManage: false });
    const card = await screen.findByRole("region", { name: "Tests de performance" });
    expect(await within(card).findByText("Sprint 30 m")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Nouveau test" })).not.toBeInTheDocument();
  });

  it("joueur ou Capitaine sans droit : « Mes tests » seulement, aucun appel au catalogue", async () => {
    renderCard({ staff: false, canManage: false });
    const card = await screen.findByRole("region", { name: "Mes tests" });
    expect(await within(card).findByText("Sprint 30 m")).toBeInTheDocument();
    expect(within(card).getByText(/Meilleur 4,52 s · dernier 4,60 s le 10 novembre 2026/)).toBeInTheDocument();
    expect(listPerformanceTests).not.toHaveBeenCalled();
    expect(within(card).queryByRole("button", { name: "Nouveau test" })).not.toBeInTheDocument();
  });

  it("refus (403) du catalogue : bascule sur « Mes tests »", async () => {
    vi.mocked(listPerformanceTests).mockRejectedValue(new ApiError(403, { detail: "Vous n'avez pas accès à cette action." }));
    renderCard({ staff: true, canManage: false });
    expect(await screen.findByRole("region", { name: "Mes tests" })).toBeInTheDocument();
    await waitFor(() => expect(getMyPerformanceOverview).toHaveBeenCalled());
  });
});

describe("PerformanceTestsCard — états", () => {
  it("staff, aucun test : message vide", async () => {
    vi.mocked(listPerformanceTests).mockResolvedValue({ results: [] });
    renderCard({ staff: true, canManage: true });
    expect(await screen.findByText("Aucun test de performance pour l'instant.")).toBeInTheDocument();
  });

  it("joueur sans mesure", async () => {
    vi.mocked(getMyPerformanceOverview).mockResolvedValue({ membership: brief(1, "Alice Durand"), tests: [] });
    renderCard({ staff: false, canManage: false });
    expect(await screen.findByText("Vous n'avez pas encore de mesure.")).toBeInTheDocument();
  });

  it("erreur du catalogue avec « Réessayer »", async () => {
    vi.mocked(listPerformanceTests).mockRejectedValue(new ApiError(500, {}));
    renderCard({ staff: true, canManage: true });
    expect(await screen.findByText("Impossible de charger les tests de performance.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });

  it("tests archivés : liste dédiée, sans action d'archivage", async () => {
    const user = userEvent.setup();
    vi.mocked(listPerformanceTests).mockImplementation(async (params) =>
      params?.archived === "only" ? { results: [overview({ id: 9, name: "Ancien test", archived: true })] } : { results: [overview()] },
    );
    renderCard({ staff: true, canManage: true });
    await screen.findByText("Sprint 30 m");
    await user.click(screen.getByRole("button", { name: "Tests archivés" }));
    expect(await screen.findByText("Ancien test")).toBeInTheDocument();
  });
});

describe("PerformanceTestsCard — classement et évolution", () => {
  it("classement : changement de période, tendance en texte, évolution d'un joueur", async () => {
    const user = userEvent.setup();
    renderCard({ staff: true, canManage: true });
    await user.click(await screen.findByRole("button", { name: /Sprint 30 m/ }));
    const dialog = await screen.findByRole("dialog", { name: "Classement : Sprint 30 m" });
    expect(await within(dialog).findByText("en progrès de 0,12 s")).toBeInTheDocument();
    expect(getPerformanceLeaderboard).toHaveBeenCalledWith(1, "last");
    await user.click(within(dialog).getByRole("button", { name: "Saison" }));
    await waitFor(() => expect(getPerformanceLeaderboard).toHaveBeenCalledWith(1, "season"));

    await user.click(await within(dialog).findByText("Alice Durand"));
    const evo = await screen.findByRole("dialog", { name: "Évolution : Sprint 30 m — Alice Durand" });
    expect(getPlayerPerformanceEvolution).toHaveBeenCalledWith(1, 1);
    expect(await within(evo).findByText("en progrès de 0,31 s depuis la première mesure")).toBeInTheDocument();
    expect(within(evo).getByText("Plus bas = plus rapide")).toBeInTheDocument();
    expect(within(evo).getByText("Meilleur")).toBeInTheDocument();
  });

  it("joueur : « Mon évolution » sans jamais demander celle d'un autre", async () => {
    const user = userEvent.setup();
    renderCard({ staff: false, canManage: false });
    await user.click(await screen.findByRole("button", { name: /Sprint 30 m/ }));
    const evo = await screen.findByRole("dialog", { name: "Mon évolution : Sprint 30 m" });
    expect(await within(evo).findByText("Progression")).toBeInTheDocument();
    expect(getMyPerformanceEvolution).toHaveBeenCalledWith(1);
    expect(getPlayerPerformanceEvolution).not.toHaveBeenCalled();
  });

  it("Coach : archivage avec confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(archivePerformanceTest).mockResolvedValue(makeTest({ archived: true }));
    renderCard({ staff: true, canManage: true });
    await user.click(await screen.findByRole("button", { name: /Sprint 30 m/ }));
    const dialog = await screen.findByRole("dialog", { name: "Classement : Sprint 30 m" });
    await user.click(within(dialog).getByRole("button", { name: "Archiver le test" }));
    const confirm = await screen.findByRole("dialog", { name: "Archiver le test « Sprint 30 m » ?" });
    expect(within(confirm).getByText(/Ses résultats restent consultables/)).toBeInTheDocument();
    await user.click(within(confirm).getByRole("button", { name: "Archiver" }));
    await waitFor(() => expect(archivePerformanceTest).toHaveBeenCalledWith(1));
  });

  it("Président : le classement n'offre ni modification ni archivage", async () => {
    const user = userEvent.setup();
    renderCard({ staff: true, canManage: false });
    await user.click(await screen.findByRole("button", { name: /Sprint 30 m/ }));
    const dialog = await screen.findByRole("dialog", { name: "Classement : Sprint 30 m" });
    expect(within(dialog).queryByRole("button", { name: "Archiver le test" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Modifier le test" })).not.toBeInTheDocument();
  });
});

describe("TestFormModal", () => {
  it("part d'un modèle, affiche l'aide santé et envoie le corps exact", async () => {
    const user = userEvent.setup();
    vi.mocked(createPerformanceTest).mockResolvedValue(makeTest({ id: 5, name: "Sprint 10 m" }));
    renderCard({ staff: true, canManage: true });
    await user.click(await screen.findByRole("button", { name: "Nouveau test" }));
    const dialog = await screen.findByRole("dialog", { name: "Nouveau test" });

    // L'aide « santé » vient de l'API et c'est le seul endroit où ces mots apparaissent.
    expect(await within(dialog).findByText(HEALTH_HELP)).toBeInTheDocument();
    for (const forbidden of [/\bkg\b/i, /battements/i, /tension/i, /VO2/i]) {
      expect(within(dialog).queryByText(forbidden)).not.toBeInTheDocument();
    }

    await user.click(await within(dialog).findByRole("button", { name: "Sprint 10 m" }));
    expect(within(dialog).getByLabelText("Nom")).toHaveValue("Sprint 10 m");
    expect(within(dialog).getByLabelText("Distance (m)")).toHaveValue("10");
    expect(createPerformanceTest).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(createPerformanceTest).toHaveBeenCalledTimes(1));
    expect(createPerformanceTest).toHaveBeenCalledWith({
      name: "Sprint 10 m",
      kind: "timed_distance",
      distance_m: "10",
      description: "Départ arrêté.",
    });
  });

  it("validation : nom obligatoire et message du serveur (nom déjà utilisé)", async () => {
    const user = userEvent.setup();
    vi.mocked(createPerformanceTest).mockRejectedValue(new ApiError(400, { detail: "Un test porte déjà ce nom." }));
    renderCard({ staff: true, canManage: true });
    await user.click(await screen.findByRole("button", { name: "Nouveau test" }));
    const dialog = await screen.findByRole("dialog", { name: "Nouveau test" });
    await user.click(within(dialog).getByRole("button", { name: "Enregistrer" }));
    expect(await within(dialog).findByText("Saisissez un nom pour le test.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Nom"), "Sprint 30 m");
    await user.type(within(dialog).getByLabelText("Distance (m)"), "30");
    await user.click(within(dialog).getByRole("button", { name: "Enregistrer" }));
    expect(await within(dialog).findByText("Un test porte déjà ce nom.")).toBeInTheDocument();
  });

  it("saisie libre : unité dans une liste fermée, sans unité de santé", async () => {
    const user = userEvent.setup();
    renderCard({ staff: true, canManage: true });
    await user.click(await screen.findByRole("button", { name: "Nouveau test" }));
    const dialog = await screen.findByRole("dialog", { name: "Nouveau test" });
    await user.click(within(dialog).getByRole("button", { name: "Saisie libre" }));
    const units = within(within(dialog).getByRole("group", { name: "Unité" })).getAllByRole("button").map((b) => b.textContent);
    expect(units).toEqual(["secondes", "mètres", "km/h", "répétitions", "points", "pourcentage"]);
    await user.type(within(dialog).getByLabelText("Nom"), "Précision de passes");
    await user.click(within(dialog).getByRole("button", { name: "pourcentage" }));
    await user.click(within(dialog).getByRole("button", { name: "Le plus bas" }));
    vi.mocked(createPerformanceTest).mockResolvedValue(makeTest({ id: 6 }));
    await user.click(within(dialog).getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(createPerformanceTest).toHaveBeenCalled());
    expect(createPerformanceTest).toHaveBeenCalledWith({
      name: "Précision de passes",
      kind: "free",
      description: "",
      unit: "percent",
      decimals: 0,
      higher_is_better: false,
    });
  });

  it("test avec résultats : type et paramètres verrouillés, seuls nom et description partent", async () => {
    const user = userEvent.setup();
    vi.mocked(updatePerformanceTest).mockResolvedValue(makeTest());
    renderCard({ staff: true, canManage: true });
    await user.click(await screen.findByRole("button", { name: /Sprint 30 m/ }));
    await user.click(await screen.findByRole("button", { name: "Modifier le test" }));
    const dialog = await screen.findByRole("dialog", { name: "Modifier le test" });
    expect(within(dialog).getByText(/Le type ne peut plus changer : des résultats existent\./)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Saisie libre" })).toBeDisabled();
    expect(within(dialog).getByLabelText("Distance (m)")).toBeDisabled();
    const name = within(dialog).getByLabelText("Nom");
    await user.clear(name);
    await user.type(name, "Sprint 30 m (départ lancé)");
    await user.click(within(dialog).getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(updatePerformanceTest).toHaveBeenCalledTimes(1));
    expect(updatePerformanceTest).toHaveBeenCalledWith(1, { name: "Sprint 30 m (départ lancé)", description: "" });
  });
});

describe("Aucun terme de santé hors de l'aide serveur", () => {
  it("la carte et le classement n'affichent aucun terme de santé", async () => {
    const user = userEvent.setup();
    renderCard({ staff: true, canManage: true });
    await user.click(await screen.findByRole("button", { name: /Sprint 30 m/ }));
    await screen.findByRole("dialog", { name: "Classement : Sprint 30 m" });
    await waitFor(() => expect(getPerformanceLeaderboard).toHaveBeenCalled());
    expect(document.body.textContent ?? "").not.toMatch(/poids|taille|cardiaque|battements|tension|VO2|diagnostic|blessure|inapte/i);
  });
});
