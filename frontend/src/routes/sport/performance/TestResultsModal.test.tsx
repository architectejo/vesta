import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client";
import { ToastProvider } from "../../../design-system";
import { TestResultsModal } from "./TestResultsModal";
import { brief, makeDetail, makeResults, makeRow, makeValue, profileWith } from "./testFixtures";

vi.mock("../../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../../api/clubs")>("../../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});
vi.mock("../../../api/performance", async () => {
  const actual = await vi.importActual<typeof import("../../../api/performance")>("../../../api/performance");
  return {
    ...actual,
    getEventPerformanceResults: vi.fn(),
    getPerformanceResult: vi.fn(),
    correctPerformanceResult: vi.fn(),
    voidPerformanceResult: vi.fn(),
  };
});
import { getMyProfile } from "../../../api/clubs";
import {
  correctPerformanceResult,
  getEventPerformanceResults,
  getPerformanceResult,
  voidPerformanceResult,
} from "../../../api/performance";

function renderModal(onMeasureMore?: (testId: number) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <TestResultsModal open onClose={() => undefined} eventId={7} testId={1} testName="Sprint 30 m" onMeasureMore={onMeasureMore} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  vi.mocked(getMyProfile).mockResolvedValue(profileWith("coach"));
  vi.mocked(getEventPerformanceResults).mockResolvedValue(makeResults());
  vi.mocked(getPerformanceResult).mockResolvedValue(makeDetail());
  vi.mocked(correctPerformanceResult).mockReset();
  vi.mocked(voidPerformanceResult).mockReset();
  consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
  vi.clearAllMocks();
});

describe("TestResultsModal — classement de la séance", () => {
  it("affiche le résumé, le rang, la valeur servie par l'API, la vitesse et le record personnel", async () => {
    renderModal();
    expect(await screen.findByText(/Sprint 30 m — séance du 10 novembre 2026/)).toBeInTheDocument();
    expect(screen.getByText("2 joueurs mesurés · meilleur 4,21 s · moyenne 4,63 s")).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]!).getByText("4,21 s")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("23,9 km/h")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Record personnel")).toBeInTheDocument();
    expect(within(rows[1]!).getByText(/Essai 2 sur 2/)).toBeInTheDocument();
    expect(within(rows[1]!).queryByText("Record personnel")).not.toBeInTheDocument();
  });

  it("place les abandons à part, jamais classés", async () => {
    vi.mocked(getEventPerformanceResults).mockResolvedValue(
      makeResults({
        results: [makeRow()],
        dnf: [
          {
            id: 30,
            player: brief(3, "Carl Petit"),
            attempt_no: 1,
            method: "stopwatch",
            ...makeValue({ outcome: "dnf", time_ms: null, display: "Abandon", derived: {} }),
          },
        ],
      }),
    );
    renderModal();
    const section = await screen.findByRole("region", { name: "Abandons" });
    expect(within(section).getByText("Carl Petit")).toBeInTheDocument();
  });

  it("joueur : sa seule ligne et son meilleur résultat, sans rang ni classement", async () => {
    vi.mocked(getMyProfile).mockResolvedValue(profileWith("player"));
    vi.mocked(getEventPerformanceResults).mockResolvedValue(
      makeResults({
        scope: "mine",
        results: [makeRow({ rank: 1 })],
        my_best_overall: { date: "2026-10-01", ...makeValue({ time_ms: 4450, display: "4,45 s" }) },
      }),
    );
    renderModal(() => undefined);
    expect(await screen.findByText(/Votre meilleur résultat sur ce test :/)).toBeInTheDocument();
    expect(screen.getByText("4,45 s")).toBeInTheDocument();
    expect(screen.queryByText(/joueurs mesurés/)).not.toBeInTheDocument();
    // Un joueur ne mesure pas : pas de bouton « Ajouter des mesures ».
    expect(screen.queryByRole("button", { name: "Ajouter des mesures" })).not.toBeInTheDocument();
  });

  it("fenêtre fermée : lecture seule, plus d'ajout de mesures", async () => {
    vi.mocked(getEventPerformanceResults).mockResolvedValue(makeResults({ window_open: false }));
    renderModal(() => undefined);
    expect(await screen.findByText("La période de saisie des mesures est terminée : lecture seule.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ajouter des mesures" })).not.toBeInTheDocument();
  });

  it("Coach, fenêtre ouverte : « Ajouter des mesures » rouvre l'écran de mesure sur ce test", async () => {
    const user = userEvent.setup();
    const onMeasureMore = vi.fn();
    renderModal(onMeasureMore);
    await user.click(await screen.findByRole("button", { name: "Ajouter des mesures" }));
    expect(onMeasureMore).toHaveBeenCalledWith(1);
  });

  it("état vide", async () => {
    vi.mocked(getEventPerformanceResults).mockResolvedValue(
      makeResults({ results: [], dnf: [], summary: { measured_count: 0, best: null, average: null } }),
    );
    renderModal();
    expect(await screen.findByText("Aucune mesure pour ce test pendant cette séance.")).toBeInTheDocument();
  });

  it("état d'erreur avec « Réessayer »", async () => {
    vi.mocked(getEventPerformanceResults).mockRejectedValue(new ApiError(500, {}));
    renderModal();
    expect(await screen.findByText("Impossible de charger les résultats.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });
});

describe("TestResultsModal — correction et retrait", () => {
  async function openDetail(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: /Alice Durand/ }));
    return screen.findByRole("dialog", { name: "Résultat de Alice Durand" });
  }

  it("détail : valeur, vitesse, méthode, auteur et historique des corrections", async () => {
    const user = userEvent.setup();
    vi.mocked(getPerformanceResult).mockResolvedValue(
      makeDetail({
        corrections: [
          {
            id: 1,
            actor: { id: 9, name: "Coach Dupont" },
            created_at: "2026-11-10T12:00:00Z",
            reason: "Appui trop tardif",
            before: { status: "active", ...makeValue({ time_ms: 4510, display: "4,51 s" }) },
            after: { status: "active", ...makeValue({ time_ms: 4210, display: "4,21 s" }) },
          },
        ],
      }),
    );
    renderModal();
    const dialog = await openDetail(user);
    expect(within(dialog).getByText("23,9 km/h · 6,64 m/s")).toBeInTheDocument();
    expect(within(dialog).getByText(/Mesuré par Coach Dupont/)).toBeInTheDocument();
    const history = within(dialog).getByRole("region", { name: "Historique des corrections" });
    expect(within(history).getByText(/Corrigé par Coach Dupont/)).toHaveTextContent("4,51 s → 4,21 s · motif : Appui trop tardif");
  });

  it("correction : le motif est obligatoire, puis le corps exact est envoyé", async () => {
    const user = userEvent.setup();
    vi.mocked(correctPerformanceResult).mockResolvedValue(makeDetail({ ...makeValue({ time_ms: 4300, display: "4,30 s" }) }));
    renderModal();
    const dialog = await openDetail(user);
    await user.click(within(dialog).getByRole("button", { name: "Corriger" }));
    const field = within(dialog).getByLabelText(/Temps \(s\)/);
    await user.clear(field);
    await user.type(field, "4,30");
    await user.click(within(dialog).getByRole("button", { name: "Enregistrer la correction" }));
    expect(await within(dialog).findByText("Indiquez le motif.")).toBeInTheDocument();
    expect(correctPerformanceResult).not.toHaveBeenCalled();

    await user.type(within(dialog).getByLabelText("Motif de la correction"), "Chrono arrêté trop tôt");
    await user.click(within(dialog).getByRole("button", { name: "Enregistrer la correction" }));
    await waitFor(() => expect(correctPerformanceResult).toHaveBeenCalledTimes(1));
    expect(correctPerformanceResult).toHaveBeenCalledWith(11, { reason: "Chrono arrêté trop tôt", time_ms: 4300, outcome: "done" });
  });

  it("correction refusée par l'API : message du serveur affiché", async () => {
    const user = userEvent.setup();
    vi.mocked(correctPerformanceResult).mockRejectedValue(new ApiError(400, { detail: "Aucun changement : la valeur est identique." }));
    renderModal();
    const dialog = await openDetail(user);
    await user.click(within(dialog).getByRole("button", { name: "Corriger" }));
    await user.type(within(dialog).getByLabelText("Motif de la correction"), "Vérification");
    await user.click(within(dialog).getByRole("button", { name: "Enregistrer la correction" }));
    expect(await within(dialog).findByText("Aucun changement : la valeur est identique.")).toBeInTheDocument();
  });

  it("retrait : motif obligatoire, puis appel void", async () => {
    const user = userEvent.setup();
    vi.mocked(voidPerformanceResult).mockResolvedValue(makeDetail({ status: "voided" }));
    renderModal();
    const dialog = await openDetail(user);
    await user.click(within(dialog).getByRole("button", { name: "Retirer ce résultat" }));
    const confirm = await screen.findByRole("dialog", { name: /Retirer le résultat de Alice Durand \(4,21 s\) \?/ });
    expect(within(confirm).getByText(/restera dans l'historique des corrections/)).toBeInTheDocument();
    await user.click(within(confirm).getByRole("button", { name: "Retirer" }));
    expect(await within(confirm).findByText("Indiquez le motif.")).toBeInTheDocument();
    expect(voidPerformanceResult).not.toHaveBeenCalled();
    await user.type(within(confirm).getByLabelText("Motif"), "Mauvais joueur");
    await user.click(within(confirm).getByRole("button", { name: "Retirer" }));
    await waitFor(() => expect(voidPerformanceResult).toHaveBeenCalledWith(11, "Mauvais joueur"));
  });

  it("résultat verrouillé : bandeau, ni correction ni retrait", async () => {
    const user = userEvent.setup();
    vi.mocked(getPerformanceResult).mockResolvedValue(makeDetail({ locked: true }));
    renderModal();
    const dialog = await openDetail(user);
    expect(within(dialog).getByText("Résultat verrouillé (plus de 48 heures).")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Corriger" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Retirer ce résultat" })).not.toBeInTheDocument();
  });

  it("Président (lecture seule) : aucun bouton de correction", async () => {
    const user = userEvent.setup();
    vi.mocked(getMyProfile).mockResolvedValue(profileWith("president"));
    renderModal();
    const dialog = await openDetail(user);
    expect(within(dialog).getByText("23,9 km/h · 6,64 m/s")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Corriger" })).not.toBeInTheDocument();
  });
});
