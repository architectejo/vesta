import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PerformanceTest } from "../../../api/performance";
import type { SessionDetail } from "../../../api/sport";
import { ToastProvider } from "../../../design-system";
import { chronoDraftKey, readChronoDraft, type ChronoDraft, type CountdownSnapshot } from "./chronoDraft";
import { MeasureModal } from "./MeasureModal";
import { useMeasureOutbox } from "./useMeasureOutbox";
import { brief, bulkResponse, makeTest, makeValue } from "./testFixtures";

vi.mock("../../../api/performance", async () => {
  const actual = await vi.importActual<typeof import("../../../api/performance")>("../../../api/performance");
  return { ...actual, listPerformanceTests: vi.fn(), listPerformanceTemplates: vi.fn(), bulkPerformanceResults: vi.fn() };
});
vi.mock("../../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../../api/sport")>("../../../api/sport");
  return { ...actual, getSession: vi.fn() };
});
import { bulkPerformanceResults, listPerformanceTemplates, listPerformanceTests } from "../../../api/performance";
import { getSession } from "../../../api/sport";

const EVENT_ID = 7;
const USER_ID = 5;

function sessionDetail(): SessionDetail {
  return {
    id: EVENT_ID,
    attendances: [
      { id: 1, membership_id: 1, player: brief(1, "Alice Durand"), status: "present" },
      { id: 2, membership_id: 2, player: brief(2, "Bob Martin"), status: "present" },
    ],
  } as unknown as SessionDetail;
}

// Horloge monotone de la page et heure réelle, simulées.
let mono = 0;
let wall = 1_000_000;
const clock = () => mono;
const wallClock = () => wall;

function Harness({ userId, restore }: { userId: number | null; restore?: ChronoDraft | null }) {
  const outbox = useMeasureOutbox();
  const [open, setOpen] = useState(true);
  return (
    <>
      <MeasureModal
        open={open}
        eventId={EVENT_ID}
        outbox={outbox}
        onClose={() => setOpen(false)}
        clock={clock}
        wallClock={wallClock}
        userId={userId}
        restore={restore}
      />
      <p>{open ? "ouverte" : "fermée"}</p>
    </>
  );
}

function renderModal(
  props: { userId: number | null; restore?: ChronoDraft | null },
  tests: PerformanceTest[] = [makeTest()],
  { sessionFails = false }: { sessionFails?: boolean } = {},
) {
  vi.mocked(listPerformanceTests).mockResolvedValue({
    results: tests.map((t) => ({ ...t, last_measured_on: null, last_measured_count: 0, season_best: null })),
  });
  vi.mocked(listPerformanceTemplates).mockResolvedValue({ results: [], health_help: "" });
  if (sessionFails) vi.mocked(getSession).mockRejectedValue(new Error("hors connexion"));
  else vi.mocked(getSession).mockResolvedValue(sessionDetail());
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <Harness {...props} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

async function chooseAndStart(user: ReturnType<typeof userEvent.setup>, testName = "Sprint 30 m") {
  await user.click(await screen.findByRole("radio", { name: new RegExp(testName) }));
  await user.click(await screen.findByRole("checkbox", { name: /Alice/ }));
  await user.click(await screen.findByRole("checkbox", { name: /Bob/ }));
  await user.click(screen.getByRole("button", { name: "Commencer" }));
}

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  mono = 0;
  wall = 1_000_000;
  window.localStorage.clear();
  vi.stubGlobal("requestAnimationFrame", () => 1);
  vi.stubGlobal("cancelAnimationFrame", () => undefined);
  vi.mocked(bulkPerformanceResults).mockReset();
  consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("MeasureModal — sauvegarde locale du chrono", () => {
  it("n'écrit rien avant le départ, puis sauvegarde chaque changement", async () => {
    const user = userEvent.setup();
    renderModal({ userId: USER_ID });
    await chooseAndStart(user);
    expect(window.localStorage.getItem(chronoDraftKey(USER_ID, EVENT_ID))).toBeNull();

    mono = 1000;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    mono = 5370;
    wall = 1_004_370;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));

    const draft = readChronoDraft(USER_ID, EVENT_ID, wall);
    expect(draft).not.toBeNull();
    expect(draft!.testName).toBe("Sprint 30 m");
    expect(draft!.playerIds).toEqual([1, 2]);
    if (draft!.step !== "stopwatch") throw new Error("état inattendu");
    expect(draft!.stopwatch.runners[1]).toMatchObject({ status: "stopped", timeMs: 4370 });
    expect(draft!.stopwatch.runners[2]).toMatchObject({ status: "running" });
  });

  it("après extinction : reprend les temps pris, le chrono des joueurs en course inclut l'interruption", async () => {
    const user = userEvent.setup();
    const first = renderModal({ userId: USER_ID });
    await chooseAndStart(user);
    mono = 1000;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    mono = 5370;
    wall = 1_004_370;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));
    // Le téléphone s'éteint : la page disparaît sans fermer la modale.
    first.unmount();

    // Réouverture 2 minutes plus tard : nouvelle page, horloge monotone repartie de zéro.
    mono = 10;
    wall = 1_124_370;
    const draft = readChronoDraft(USER_ID, EVENT_ID, wall)!;
    renderModal({ userId: USER_ID, restore: draft });

    expect(await screen.findByText("4,37 s")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Arrêter Bob Martin" })).toBeInTheDocument();
    expect(screen.getByText("Chrono en cours · 1 sur 2")).toBeInTheDocument();

    // Bob est noté « Abandon » : son temps n'a plus de sens après l'interruption.
    await user.click(screen.getByRole("button", { name: "Options pour Bob Martin" }));
    await user.click(screen.getByRole("button", { name: "Abandon" }));
    expect(screen.getByText("Chrono terminé")).toBeInTheDocument();

    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([
        { membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 11, attempt_no: 1, ...makeValue({ time_ms: 4370 }) } },
        { membership_id: 2, outcome: "created", message: "", warning: "", result: { id: 12, attempt_no: 1, ...makeValue({ outcome: "dnf", time_ms: null, display: "Abandon", derived: {} }) } },
      ]),
    );
    await user.click(screen.getByRole("button", { name: "Envoyer les mesures (2)" }));
    const dialog = await screen.findByRole("dialog", { name: "Envoyer 2 mesures ?" });
    await user.click(within(dialog).getByRole("button", { name: "Envoyer les mesures" }));
    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalledTimes(1));
    const body = vi.mocked(bulkPerformanceResults).mock.calls[0]![1];
    expect(body.method).toBe("stopwatch");
    expect(body.start_mode).toBe("group");
    expect(body.items.find((item) => item.membership_id === 1)).toMatchObject({ time_ms: 4370 });

    // Envoyées : la sauvegarde est effacée.
    await waitFor(() => expect(window.localStorage.getItem(chronoDraftKey(USER_ID, EVENT_ID))).toBeNull());
  });

  it("« Abandonner » à la fermeture efface la sauvegarde", async () => {
    const user = userEvent.setup();
    renderModal({ userId: USER_ID });
    await chooseAndStart(user);
    mono = 1000;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    expect(window.localStorage.getItem(chronoDraftKey(USER_ID, EVENT_ID))).not.toBeNull();

    await user.click(screen.getAllByRole("button", { name: "Fermer" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Abandonner ces mesures ?" });
    await user.click(within(dialog).getByRole("button", { name: "Abandonner" }));
    expect(screen.getByText("fermée")).toBeInTheDocument();
    expect(window.localStorage.getItem(chronoDraftKey(USER_ID, EVENT_ID))).toBeNull();
  });

  it("sans utilisateur connu, rien n'est écrit sur le téléphone", async () => {
    const user = userEvent.setup();
    renderModal({ userId: null });
    await chooseAndStart(user);
    mono = 1000;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    expect(window.localStorage.length).toBe(0);
  });

  it("écrit aussi toutes les secondes pendant la mesure", async () => {
    const user = userEvent.setup();
    renderModal({ userId: USER_ID });
    await chooseAndStart(user);
    mono = 1000;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    const before = readChronoDraft(USER_ID, EVENT_ID, wall)!.savedAt;
    wall += 5000;
    mono += 5000;
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 1100));
    });
    expect(readChronoDraft(USER_ID, EVENT_ID, wall)!.savedAt).toBeGreaterThan(before);
  });

  it("compte à rebours écoulé pendant l'extinction : reprise directe sur la saisie des distances", async () => {
    const cooper = makeTest({ id: 3, name: "Cooper", kind: "distance_in_time", distance_m: null, duration_s: 720, unit: "meters" });
    const draft: ChronoDraft = {
      v: 1,
      userId: USER_ID,
      eventId: EVENT_ID,
      testId: 3,
      testName: "Cooper",
      startMode: "group",
      playerIds: [1, 2],
      step: "countdown",
      countdown: { startedAt: wall - 800_000, elapsed: false },
      savedAt: wall - 100_000,
    };
    renderModal({ userId: USER_ID, restore: draft }, [cooper]);
    expect(await screen.findByText("Temps écoulé. Saisissez la distance de chaque joueur.")).toBeInTheDocument();
  });

  function cooperDraft(countdown?: CountdownSnapshot): ChronoDraft {
    return {
      v: 1,
      userId: USER_ID,
      eventId: EVENT_ID,
      testId: 3,
      testName: "Cooper",
      startMode: "group",
      playerIds: [1, 2],
      step: "countdown",
      countdown: countdown ?? { startedAt: wall - 800_000, elapsed: true },
      savedAt: wall - 100_000,
    };
  }
  const cooper = () => makeTest({ id: 3, name: "Cooper", kind: "distance_in_time", distance_m: null, duration_s: 720, unit: "meters" });

  it("distances saisies après le compte à rebours : sauvegardées, puis restaurées à la reprise", async () => {
    const user = userEvent.setup();
    renderModal({ userId: USER_ID, restore: cooperDraft() }, [cooper()]);
    const fields = await screen.findAllByLabelText(/^Distance \(m\)/);
    await user.type(fields[0]!, "2450");
    await user.type(screen.getByLabelText(/Longueur du tour/), "400");
    const saved = readChronoDraft(USER_ID, EVENT_ID, wall)!;
    expect(saved.step === "countdown" && saved.countdown.entries).toMatchObject({
      lapLength: "400",
      drafts: { 1: { text: "2450" } },
    });
  });

  it("reprise avec des distances déjà saisies : elles sont réaffichées", async () => {
    renderModal(
      {
        userId: USER_ID,
        restore: cooperDraft({
          startedAt: wall - 800_000,
          elapsed: true,
          entries: { drafts: { 2: { text: "2310", laps: "", extra: "", dnf: false } }, lapLength: "" },
        }),
      },
      [cooper()],
    );
    expect(await screen.findByDisplayValue("2310")).toBeInTheDocument();
  });

  it("fermeture d'un chrono repris, même sans nouvelle saisie : confirmation demandée", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(chronoDraftKey(USER_ID, EVENT_ID), JSON.stringify(cooperDraft()));
    renderModal({ userId: USER_ID, restore: cooperDraft() }, [cooper()]);
    await screen.findByText("Temps écoulé. Saisissez la distance de chaque joueur.");
    await user.keyboard("{Escape}");
    expect(await screen.findByRole("dialog", { name: "Abandonner ces mesures ?" })).toBeInTheDocument();
    expect(window.localStorage.getItem(chronoDraftKey(USER_ID, EVENT_ID))).not.toBeNull();
  });

  it("chargement impossible pendant la reprise : message d'erreur, la sauvegarde reste intacte", async () => {
    const user = userEvent.setup();
    const draft = cooperDraft();
    const raw = JSON.stringify(draft);
    window.localStorage.setItem(chronoDraftKey(USER_ID, EVENT_ID), raw);
    renderModal({ userId: USER_ID, restore: draft }, [cooper()], { sessionFails: true });
    expect(await screen.findByText("Impossible de charger le chrono retrouvé. Vérifiez la connexion.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
    const closeButtons = screen.getAllByRole("button", { name: "Fermer" });
    await user.click(closeButtons[closeButtons.length - 1]!);
    expect(await screen.findByText("fermée")).toBeInTheDocument();
    expect(window.localStorage.getItem(chronoDraftKey(USER_ID, EVENT_ID))).toBe(raw);
  });

  it("test retiré entre-temps : message clair, rien n'est repris", async () => {
    const user = userEvent.setup();
    const draft: ChronoDraft = {
      v: 1,
      userId: USER_ID,
      eventId: EVENT_ID,
      testId: 99,
      testName: "Ancien test",
      startMode: "group",
      playerIds: [1],
      step: "stopwatch",
      stopwatch: { phase: "finished", groupStart: wall, runners: { 1: { status: "stopped", startedAt: wall, timeMs: 5000 } }, rounds: [], frozen: 5000 },
      savedAt: wall,
    };
    window.localStorage.setItem(chronoDraftKey(USER_ID, EVENT_ID), JSON.stringify(draft));
    renderModal({ userId: USER_ID, restore: draft });
    expect(await screen.findByText("Ce test n'est plus proposé : le chrono retrouvé ne peut pas être repris.")).toBeInTheDocument();
    const closeButtons = screen.getAllByRole("button", { name: "Fermer" });
    await user.click(closeButtons[closeButtons.length - 1]!);
    expect(window.localStorage.getItem(chronoDraftKey(USER_ID, EVENT_ID))).toBeNull();
  });
});
