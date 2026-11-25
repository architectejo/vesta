import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionMeasureSummary } from "../../../api/sport";
import { ToastProvider } from "../../../design-system";
import { SessionMeasuresCard } from "./SessionMeasuresCard";
import { makeResults, profileWith } from "./testFixtures";

vi.mock("../../../api/clubs", async () => {
  const actual = await vi.importActual<typeof import("../../../api/clubs")>("../../../api/clubs");
  return { ...actual, getMyProfile: vi.fn() };
});
vi.mock("../../../api/performance", async () => {
  const actual = await vi.importActual<typeof import("../../../api/performance")>("../../../api/performance");
  return { ...actual, getEventPerformanceResults: vi.fn() };
});
import { getMyProfile } from "../../../api/clubs";
import { getEventPerformanceResults } from "../../../api/performance";

const MEASURES: SessionMeasureSummary[] = [
  {
    test_id: 1,
    name: "Sprint 30 m",
    kind: "timed_distance",
    measured_count: 14,
    best: { player: { membership_id: 1, name: "Alice Durand" }, display: "4,21 s" },
  },
];

function renderCard(props: { measures?: SessionMeasureSummary[]; canMeasure: boolean; onMeasure?: (testId?: number) => void }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SessionMeasuresCard sessionId={7} measures={props.measures ?? MEASURES} canMeasure={props.canMeasure} onMeasure={props.onMeasure} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  vi.mocked(getMyProfile).mockResolvedValue(profileWith("coach"));
  vi.mocked(getEventPerformanceResults).mockResolvedValue(makeResults());
  consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
  vi.clearAllMocks();
});

describe("SessionMeasuresCard", () => {
  it("Coach / Assistant (can_measure) : ligne par test et bouton « Mesurer »", async () => {
    const user = userEvent.setup();
    const onMeasure = vi.fn();
    renderCard({ canMeasure: true, onMeasure });
    const card = screen.getByRole("region", { name: "Mesures de la séance" });
    expect(within(card).getByText("Sprint 30 m")).toBeInTheDocument();
    expect(within(card).getByText("14 joueurs mesurés · meilleur 4,21 s")).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Mesurer" }));
    expect(onMeasure).toHaveBeenCalledTimes(1);
  });

  it("Capitaine, Président, VP, DS ou joueur (can_measure faux) : aucun bouton « Mesurer »", () => {
    renderCard({ canMeasure: false, onMeasure: vi.fn() });
    expect(screen.queryByRole("button", { name: "Mesurer" })).not.toBeInTheDocument();
    expect(screen.getByText("Sprint 30 m")).toBeInTheDocument();
  });

  it("fenêtre fermée (can_measure faux pour le Coach) : lecture seule", () => {
    renderCard({ canMeasure: false, onMeasure: vi.fn() });
    expect(screen.queryByRole("button", { name: "Mesurer" })).not.toBeInTheDocument();
  });

  it("modale « Séance » en lecture seule (pas de onMeasure) : jamais de bouton, même avec le droit", () => {
    renderCard({ canMeasure: true });
    expect(screen.queryByRole("button", { name: "Mesurer" })).not.toBeInTheDocument();
  });

  it("état vide : message explicite", () => {
    renderCard({ measures: [], canMeasure: true, onMeasure: vi.fn() });
    expect(screen.getByText("Aucune mesure pendant cette séance.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mesurer" })).toBeInTheDocument();
  });

  it("joueur : seulement sa mesure, au singulier", () => {
    renderCard({
      canMeasure: false,
      measures: [{ ...MEASURES[0]!, measured_count: 1, best: { player: { membership_id: 5, name: "Moi" }, display: "4,45 s" } }],
    });
    expect(screen.getByText("1 joueur mesuré · meilleur 4,45 s")).toBeInTheDocument();
  });

  it("un clic sur une ligne ouvre le classement du test pour cette séance", async () => {
    const user = userEvent.setup();
    renderCard({ canMeasure: true, onMeasure: vi.fn() });
    await user.click(screen.getByRole("button", { name: /Sprint 30 m/ }));
    expect(await screen.findByText(/Sprint 30 m — séance du 10 novembre 2026/)).toBeInTheDocument();
    expect(getEventPerformanceResults).toHaveBeenCalledWith(7, 1);
  });

  it("« Ajouter des mesures » ferme les résultats et rouvre l'écran de mesure sur ce test", async () => {
    const user = userEvent.setup();
    const onMeasure = vi.fn();
    renderCard({ canMeasure: true, onMeasure });
    await user.click(screen.getByRole("button", { name: /Sprint 30 m/ }));
    await user.click(await screen.findByRole("button", { name: "Ajouter des mesures" }));
    expect(onMeasure).toHaveBeenCalledWith(1);
  });
});
