import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client";
import type { BulkPerformanceInput, PerformanceTest } from "../../../api/performance";
import type { SessionDetail } from "../../../api/sport";
import { ToastProvider } from "../../../design-system";
import { MeasureModal } from "./MeasureModal";
import { PendingMeasures } from "./PendingMeasures";
import { MEASURE_QUEUE_KEY, REFUSED_MEASURES_KEY, useMeasureOutbox } from "./useMeasureOutbox";
import { brief, bulkResponse, makeTest, makeValue } from "./testFixtures";

vi.mock("../../../api/performance", async () => {
  const actual = await vi.importActual<typeof import("../../../api/performance")>("../../../api/performance");
  return {
    ...actual,
    listPerformanceTests: vi.fn(),
    listPerformanceTemplates: vi.fn(),
    bulkPerformanceResults: vi.fn(),
  };
});
vi.mock("../../../api/sport", async () => {
  const actual = await vi.importActual<typeof import("../../../api/sport")>("../../../api/sport");
  return { ...actual, getSession: vi.fn() };
});
import { bulkPerformanceResults, listPerformanceTemplates, listPerformanceTests } from "../../../api/performance";
import { getSession } from "../../../api/sport";

const EVENT_ID = 7;

function attendance(id: number, name: string, status: "present" | "late_absent" | "absent") {
  return { id, membership_id: id, player: brief(id, name), status };
}

function sessionDetail(): SessionDetail {
  // Seuls les pointages sont lus par l'écran de mesure.
  return {
    id: EVENT_ID,
    attendances: [
      attendance(1, "Alice Durand", "present"),
      attendance(2, "Bob Martin", "present"),
      attendance(3, "Carl Petit", "late_absent"),
      attendance(4, "Dan Absent", "absent"),
    ],
  } as unknown as SessionDetail;
}

// --- horloge et animation simulées -------------------------------------------------------------
let now = 0;
const clock = () => now;
let frames: FrameRequestCallback[] = [];
let frameTime = 0;
function tick() {
  frameTime += 1000;
  act(() => {
    const callbacks = frames;
    frames = [];
    callbacks.forEach((callback) => callback(frameTime));
  });
}

function Harness({ initialTestId }: { initialTestId?: number }) {
  const outbox = useMeasureOutbox();
  const [open, setOpen] = useState(true);
  return (
    <>
      <MeasureModal open={open} eventId={EVENT_ID} outbox={outbox} onClose={() => setOpen(false)} clock={clock} initialTestId={initialTestId} />
      <PendingMeasures outbox={outbox} eventId={EVENT_ID} />
      <p>{open ? "ouverte" : "fermée"}</p>
    </>
  );
}

function renderModal(tests: PerformanceTest[] = [makeTest()], initialTestId?: number) {
  vi.mocked(listPerformanceTests).mockResolvedValue({ results: tests.map((t) => ({ ...t, last_measured_on: null, last_measured_count: 0, season_best: null })) });
  vi.mocked(listPerformanceTemplates).mockResolvedValue({ results: [], health_help: "" });
  vi.mocked(getSession).mockResolvedValue(sessionDetail());
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <Harness initialTestId={initialTestId} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

async function chooseAndStart(user: ReturnType<typeof userEvent.setup>, players: string[], testName = "Sprint 30 m") {
  await user.click(await screen.findByRole("radio", { name: new RegExp(testName) }));
  for (const player of players) await user.click(await screen.findByRole("checkbox", { name: new RegExp(player) }));
  await user.click(screen.getByRole("button", { name: "Commencer" }));
}

function sentBody(call = 0): BulkPerformanceInput {
  return vi.mocked(bulkPerformanceResults).mock.calls[call]![1];
}

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  now = 0;
  frames = [];
  frameTime = 0;
  window.localStorage.clear();
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.push(callback);
    return frames.length;
  });
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

describe("MeasureModal — choix", () => {
  it("ne propose que les joueurs pointés et jamais de liste déroulante", async () => {
    const user = userEvent.setup();
    renderModal();
    await screen.findByRole("radio", { name: /Sprint 30 m/ });
    expect(await screen.findByRole("checkbox", { name: /Alice/ })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Carl/ })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Dan Absent/ })).not.toBeInTheDocument();
    expect(document.querySelector("select")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Commencer" }));
    expect(await screen.findByText("Choisissez un test.")).toBeInTheDocument();
  });

  it("ramène à l'écran le bandeau d'erreur, placé en haut alors que « Commencer » est dans le pied collant (360 px)", async () => {
    // Vérification visuelle B3 : avec plus de 12 joueurs en départ groupé, la
    // liste défilée cachait l'erreur et l'appui semblait sans effet.
    const scrollIntoView = vi.fn();
    Object.defineProperty(Element.prototype, "scrollIntoView", { value: scrollIntoView, configurable: true, writable: true });
    try {
      const user = userEvent.setup();
      renderModal();
      await screen.findByRole("radio", { name: /Sprint 30 m/ });
      await user.click(screen.getByRole("button", { name: "Commencer" }));
      const banner = await screen.findByText("Choisissez un test.");
      await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" }));
      expect(scrollIntoView.mock.contexts.at(-1)).toContainElement(banner);
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });

  it("propose le chronomètre seulement pour les tests chronométrables", async () => {
    const user = userEvent.setup();
    renderModal([makeTest({ id: 2, name: "Tirs cadrés", kind: "repetitions", stopwatch_available: false, attempts: 10, distance_m: null })]);
    await user.click(await screen.findByRole("radio", { name: /Tirs cadrés/ }));
    expect(screen.queryByRole("button", { name: "Chronomètre" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Saisie manuelle" })).toBeInTheDocument();
  });

  it("état vide des tests : message et action « Nouveau test »", async () => {
    renderModal([]);
    expect(await screen.findByText("Aucun test de performance pour l'instant.")).toBeInTheDocument();
  });
});

describe("MeasureModal — chrono groupé", () => {
  it("départ groupé, arrêt individuel, annulation d'un arrêt, temps en ms entières, vitesse indicative, envoi exact", async () => {
    const user = userEvent.setup();
    renderModal();
    await chooseAndStart(user, ["Alice", "Bob", "Carl"]);

    expect(screen.getByRole("timer")).toHaveTextContent("00:00,00");
    // Aucun bouton d'arrêt avant le départ.
    expect(screen.queryByRole("button", { name: /^Arrêter / })).not.toBeInTheDocument();

    now = 1000;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    now = 5370;
    tick();
    expect(screen.getByRole("timer")).toHaveTextContent("00:04,37");

    // Alice s'arrête par erreur à 4,37 s : vitesse indicative affichée.
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));
    expect(screen.getByText("4,37 s")).toBeInTheDocument();
    expect(screen.getByText(/24,7\s+km\/h \(indicatif\)/)).toBeInTheDocument();

    // Annulation de l'arrêt : le chrono d'Alice repart du chrono commun.
    await user.click(screen.getByRole("button", { name: "Reprendre le chrono de Alice Durand" }));
    expect(screen.getByRole("button", { name: "Arrêter Alice Durand" })).toBeInTheDocument();

    now = 5400;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));
    expect(screen.getByText("4,40 s")).toBeInTheDocument();

    now = 6000;
    await user.click(screen.getByRole("button", { name: "Arrêter Bob Martin" }));
    // Carl abandonne (tombé) via le menu de sa ligne.
    await user.click(screen.getByRole("button", { name: "Options pour Carl Petit" }));
    await user.click(screen.getByRole("button", { name: "Abandon" }));

    // Tout le monde est arrêté : le chrono s'arrête seul.
    expect(screen.getByText("Chrono terminé")).toBeInTheDocument();

    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([
        { membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 11, attempt_no: 1, ...makeValue({ time_ms: 4400 }) } },
        { membership_id: 2, outcome: "created", message: "", warning: "", result: { id: 12, attempt_no: 1, ...makeValue({ time_ms: 5000 }) } },
        { membership_id: 3, outcome: "created", message: "", warning: "", result: { id: 13, attempt_no: 1, ...makeValue({ outcome: "dnf", time_ms: null, display: "Abandon", derived: {} }) } },
      ]),
    );
    await user.click(screen.getByRole("button", { name: "Enregistrer (3)" }));
    const dialog = await screen.findByRole("dialog", { name: "Envoyer 3 mesures ?" });
    expect(within(dialog).getByText("4,40 s")).toBeInTheDocument();
    expect(within(dialog).getByText("5,00 s")).toBeInTheDocument();
    expect(within(dialog).getByText("Abandon")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Envoyer les mesures" }));

    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalledTimes(1));
    const [eventId, body] = vi.mocked(bulkPerformanceResults).mock.calls[0]!;
    expect(eventId).toBe(EVENT_ID);
    expect(body).toEqual({
      test_id: 1,
      method: "stopwatch",
      start_mode: "group",
      client_uuid: expect.any(String),
      items: [
        { membership_id: 1, attempt_no: 1, time_ms: 4400, client_uuid: expect.any(String) },
        { membership_id: 2, attempt_no: 1, time_ms: 5000, client_uuid: expect.any(String) },
        { membership_id: 3, attempt_no: 1, outcome: "dnf", client_uuid: expect.any(String) },
      ],
    });
    for (const item of body.items) {
      if (item.time_ms !== undefined) expect(Number.isInteger(item.time_ms)).toBe(true);
    }
    // Aucune vitesse n'est envoyée : elle est recalculée par le serveur.
    expect(JSON.stringify(body)).not.toMatch(/speed|vitesse/);
    expect(await screen.findByText("3 mesures enregistrées.")).toBeInTheDocument();
  });

  it("garde les mêmes client_uuid quand l'envoi échoue puis est réessayé", async () => {
    const user = userEvent.setup();
    renderModal();
    await chooseAndStart(user, ["Alice"]);
    now = 100;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    now = 4600;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));

    vi.mocked(bulkPerformanceResults)
      .mockRejectedValueOnce(new ApiError(500, {}))
      .mockResolvedValueOnce(
        bulkResponse([{ membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 1, attempt_no: 1, ...makeValue() } }]),
      );
    await user.click(screen.getByRole("button", { name: "Enregistrer (1)" }));
    let dialog = await screen.findByRole("dialog", { name: "Envoyer 1 mesure ?" });
    await user.click(within(dialog).getByRole("button", { name: "Envoyer les mesures" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Une erreur est survenue");

    dialog = screen.getByRole("dialog", { name: "Envoyer 1 mesure ?" });
    await user.click(within(dialog).getByRole("button", { name: "Envoyer les mesures" }));
    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalledTimes(2));
    expect(sentBody(1).client_uuid).toBe(sentBody(0).client_uuid);
    expect(sentBody(1).items[0]!.client_uuid).toBe(sentBody(0).items[0]!.client_uuid);
  });

  it("affiche les refus par joueur sans perdre les autres, et garde la mesure refusée sur le téléphone", async () => {
    const user = userEvent.setup();
    renderModal();
    await chooseAndStart(user, ["Alice", "Bob"]);
    now = 10;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    now = 4510;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));
    now = 5010;
    await user.click(screen.getByRole("button", { name: "Arrêter Bob Martin" }));

    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([
        {
          membership_id: 1,
          outcome: "created",
          message: "",
          warning: "Ce temps paraît trop court pour 30 m (moins de 2,4 s) : vérifiez-le.",
          result: { id: 1, attempt_no: 1, ...makeValue() },
        },
        { membership_id: 2, outcome: "refused", message: "Bob Martin est inapte : il ne peut pas être mesuré.", warning: "", result: null },
      ]),
    );
    await user.click(screen.getByRole("button", { name: "Enregistrer (2)" }));
    const dialog = await screen.findByRole("dialog", { name: "Envoyer 2 mesures ?" });
    await user.click(within(dialog).getByRole("button", { name: "Envoyer les mesures" }));

    expect(await screen.findByText("1 mesure enregistrée.")).toBeInTheDocument();
    expect(screen.getByText(/Alice Durand : Ce temps paraît trop court/)).toBeInTheDocument();
    const refused = screen.getByRole("region", { name: "Mesures refusées" });
    expect(within(refused).getByText(/Bob Martin est inapte : il ne peut pas être mesuré\./)).toBeInTheDocument();

    // La mesure refusée reste sur le téléphone (consultable, à réessayer).
    const stored = JSON.parse(window.localStorage.getItem(REFUSED_MEASURES_KEY) ?? "[]") as Array<{ name: string; message: string }>;
    expect(stored).toHaveLength(1);
    expect(stored[0]!.name).toBe("Bob Martin");
    const local = await screen.findByRole("region", { name: "Mesures non envoyées" });
    expect(within(local).getByText(/Bob Martin est inapte/)).toBeInTheDocument();
    expect(within(local).getByText(/5,00 s/)).toBeInTheDocument();
  });

  it("« Terminer » demande confirmation et note les joueurs non arrêtés « Abandon »", async () => {
    const user = userEvent.setup();
    renderModal();
    await chooseAndStart(user, ["Alice", "Bob"]);
    now = 10;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    now = 4010;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));
    await user.click(screen.getByRole("button", { name: "Terminer" }));
    const dialog = await screen.findByRole("dialog", { name: "Arrêter le chrono ?" });
    expect(within(dialog).getByText(/1 joueur n'a pas été arrêté : il sera noté « Abandon »\./)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Arrêter" }));
    expect(screen.getByText("Chrono terminé")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enregistrer (2)" })).toBeInTheDocument();
  });

  it("plusieurs essais : « Nouvel essai » numérote l'essai suivant", async () => {
    const user = userEvent.setup();
    renderModal();
    await chooseAndStart(user, ["Alice"]);
    now = 0;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    now = 4000;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));
    await user.click(screen.getByRole("button", { name: "Nouvel essai" }));
    now = 10_000;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    now = 13_900;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));

    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([
        { membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 1, attempt_no: 1, ...makeValue() } },
        { membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 2, attempt_no: 2, ...makeValue() } },
      ]),
    );
    await user.click(screen.getByRole("button", { name: "Enregistrer (2)" }));
    const dialog = await screen.findByRole("dialog", { name: "Envoyer 2 mesures ?" });
    await user.click(within(dialog).getByRole("button", { name: "Envoyer les mesures" }));
    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalled());
    expect(sentBody().items.map((item) => [item.attempt_no, item.time_ms])).toEqual([
      [1, 4000],
      [2, 3900],
    ]);
    const uuids = sentBody().items.map((item) => item.client_uuid);
    expect(new Set(uuids).size).toBe(2);
  });

  it("départ individuel : une seule ligne active à la fois", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(await screen.findByRole("radio", { name: /Sprint 30 m/ }));
    await user.click(screen.getByRole("button", { name: "Un par un" }));
    await user.click(await screen.findByRole("checkbox", { name: /Alice/ }));
    await user.click(screen.getByRole("checkbox", { name: /Bob/ }));
    await user.click(screen.getByRole("button", { name: "Commencer" }));

    expect(screen.getByRole("button", { name: "Départ de Alice Durand" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Départ de Bob Martin" })).not.toBeInTheDocument();
    now = 100;
    await user.click(screen.getByRole("button", { name: "Départ de Alice Durand" }));
    now = 4100;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));
    expect(screen.getByText("4,00 s")).toBeInTheDocument();
    // La ligne suivante devient active automatiquement.
    expect(screen.getByRole("button", { name: "Départ de Bob Martin" })).toBeInTheDocument();
  });

  it("garde l'écran allumé : bandeau de repli sans Wake Lock", async () => {
    const user = userEvent.setup();
    renderModal();
    await chooseAndStart(user, ["Alice"]);
    await user.click(screen.getByRole("button", { name: "Départ" }));
    expect(screen.getByText("Gardez l'écran allumé pendant le chrono.")).toBeInTheDocument();
  });

  it("demande le Wake Lock quand le navigateur le permet", async () => {
    const release = vi.fn().mockResolvedValue(undefined);
    const request = vi.fn().mockResolvedValue({ release, addEventListener: vi.fn() });
    Object.defineProperty(navigator, "wakeLock", { configurable: true, value: { request } });
    try {
      const user = userEvent.setup();
      renderModal();
      await chooseAndStart(user, ["Alice"]);
      await user.click(screen.getByRole("button", { name: "Départ" }));
      await waitFor(() => expect(request).toHaveBeenCalledWith("screen"));
      await waitFor(() => expect(screen.queryByText("Gardez l'écran allumé pendant le chrono.")).not.toBeInTheDocument());
    } finally {
      Reflect.deleteProperty(navigator, "wakeLock");
    }
  });

  it("avertit avant de quitter avec des mesures non envoyées", async () => {
    const user = userEvent.setup();
    renderModal();
    await chooseAndStart(user, ["Alice"]);
    await user.click(screen.getByRole("button", { name: "Départ" }));
    await user.click(screen.getAllByRole("button", { name: "Fermer" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Abandonner ces mesures ?" });
    expect(within(dialog).getByText("Les temps non enregistrés seront perdus.")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Continuer" }));
    expect(screen.getByText("ouverte")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Abandonner ces mesures ?" })).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Fermer" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Abandonner ces mesures ?" })).getByRole("button", { name: "Abandonner" }));
    expect(screen.getByText("fermée")).toBeInTheDocument();
  });
});

describe("MeasureModal — hors connexion", () => {
  it("met le lot en file avec ses client_uuid puis l'envoie au retour du réseau", async () => {
    const user = userEvent.setup();
    const onLine = vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
    renderModal();
    await chooseAndStart(user, ["Alice"]);
    now = 0;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    now = 4520;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));
    await user.click(screen.getByRole("button", { name: "Enregistrer (1)" }));
    const dialog = await screen.findByRole("dialog", { name: "Envoyer 1 mesure ?" });
    await user.click(within(dialog).getByRole("button", { name: "Envoyer les mesures" }));

    await waitFor(() => expect(screen.getByText("fermée")).toBeInTheDocument());
    expect(bulkPerformanceResults).not.toHaveBeenCalled();
    expect(await screen.findByText(/Hors connexion — 1 en attente/)).toBeInTheDocument();
    const queued = JSON.parse(window.localStorage.getItem(MEASURE_QUEUE_KEY) ?? "[]") as Array<{ payload: { body: BulkPerformanceInput } }>;
    expect(queued).toHaveLength(1);
    const queuedBody = queued[0]!.payload.body;
    expect(queuedBody.items[0]).toMatchObject({ membership_id: 1, time_ms: 4520, attempt_no: 1 });
    expect(queuedBody.items[0]!.client_uuid).toEqual(expect.any(String));

    // Retour du réseau : le même corps part, avec les mêmes identifiants.
    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([{ membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 1, attempt_no: 1, ...makeValue() } }]),
    );
    onLine.mockReturnValue(true);
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalledTimes(1));
    expect(sentBody()).toEqual(queuedBody);
    await waitFor(() => expect(window.localStorage.getItem(MEASURE_QUEUE_KEY)).toBe("[]"));
  });

  it("un échec réseau à l'envoi met aussi le lot en file", async () => {
    const user = userEvent.setup();
    renderModal();
    await chooseAndStart(user, ["Alice"]);
    now = 0;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    now = 4000;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));
    vi.mocked(bulkPerformanceResults).mockRejectedValueOnce(new ApiError(0, null)).mockImplementation(() => new Promise(() => undefined));
    await user.click(screen.getByRole("button", { name: "Enregistrer (1)" }));
    const dialog = await screen.findByRole("dialog", { name: "Envoyer 1 mesure ?" });
    await user.click(within(dialog).getByRole("button", { name: "Envoyer les mesures" }));
    await waitFor(() => expect(screen.getByText("fermée")).toBeInTheDocument());
    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalledTimes(2));
    expect(sentBody(1)).toEqual(sentBody(0));
  });

  it("un envoi tardif refusé (fenêtre fermée) garde la mesure avec le message du serveur", async () => {
    const user = userEvent.setup();
    renderModal();
    await chooseAndStart(user, ["Alice"]);
    now = 0;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    now = 4000;
    await user.click(screen.getByRole("button", { name: "Arrêter Alice Durand" }));
    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([
        {
          membership_id: 1,
          outcome: "refused",
          message: "La période de saisie des mesures (48 h après le début de la séance) est terminée.",
          warning: "",
          result: null,
        },
      ]),
    );
    await user.click(screen.getByRole("button", { name: "Enregistrer (1)" }));
    const dialog = await screen.findByRole("dialog", { name: "Envoyer 1 mesure ?" });
    await user.click(within(dialog).getByRole("button", { name: "Envoyer les mesures" }));
    const local = await screen.findByRole("region", { name: "Mesures non envoyées" });
    expect(within(local).getByText(/La période de saisie des mesures/)).toBeInTheDocument();
    expect(within(local).getByRole("button", { name: "Réessayer" })).toBeInTheDocument();

    // Réessayer renvoie la même mesure avec le même identifiant.
    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([{ membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 1, attempt_no: 1, ...makeValue() } }]),
    );
    await user.click(within(local).getByRole("button", { name: "Réessayer" }));
    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalledTimes(2));
    expect(sentBody(1).items[0]!.client_uuid).toBe(sentBody(0).items[0]!.client_uuid);
    await waitFor(() => expect(screen.queryByRole("region", { name: "Mesures non envoyées" })).not.toBeInTheDocument());
  });
});

describe("MeasureModal — saisie manuelle", () => {
  it("temps saisi à la main : millisecondes entières, méthode manuelle, aucun start_mode", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(await screen.findByRole("radio", { name: /Sprint 30 m/ }));
    await user.click(screen.getByRole("button", { name: "Saisie manuelle" }));
    await user.click(await screen.findByRole("checkbox", { name: /Alice/ }));
    await user.click(screen.getByRole("checkbox", { name: /Bob/ }));
    await user.click(screen.getByRole("button", { name: "Commencer" }));

    expect(screen.getByText("0 résultat saisi sur 2 joueurs")).toBeInTheDocument();
    const fields = screen.getAllByLabelText(/Temps \(s\)/);
    await user.type(fields[0]!, "abc");
    expect(await screen.findByText("Saisissez un temps supérieur à 0.")).toBeInTheDocument();
    await user.clear(fields[0]!);
    await user.type(fields[0]!, "4,52");
    expect(screen.getByText("1 résultat saisi sur 2 joueurs")).toBeInTheDocument();

    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([{ membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 1, attempt_no: 1, ...makeValue() } }]),
    );
    await user.click(screen.getByRole("button", { name: "Enregistrer (1)" }));
    const dialog = await screen.findByRole("dialog", { name: "Envoyer 1 mesure ?" });
    await user.click(within(dialog).getByRole("button", { name: "Envoyer les mesures" }));
    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalled());
    expect(sentBody()).toEqual({
      test_id: 1,
      method: "manual",
      start_mode: "",
      client_uuid: expect.any(String),
      items: [{ membership_id: 1, attempt_no: 1, time_ms: 4520, client_uuid: expect.any(String) }],
    });
  });

  it("répétitions : compteur − / + et « sur N » ; une ligne vide n'est pas envoyée", async () => {
    const user = userEvent.setup();
    const test = makeTest({ id: 2, name: "Tirs cadrés sur 10", kind: "repetitions", stopwatch_available: false, attempts: 10, distance_m: null, unit: "repetitions" });
    renderModal([test]);
    await chooseAndStart(user, ["Alice", "Bob"], "Tirs cadrés");
    expect(screen.getAllByText(/Nombre réussi \(sur 10\)/)).toHaveLength(2);
    const plus = screen.getByRole("button", { name: "Ajouter une répétition pour Alice Durand" });
    await user.click(plus);
    await user.click(plus);
    await user.click(plus);
    await user.click(screen.getByRole("button", { name: "Retirer une répétition pour Alice Durand" }));

    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([{ membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 1, attempt_no: 1, ...makeValue({ count: 2, time_ms: null, display: "2 sur 10", derived: {} }) } }]),
    );
    await user.click(screen.getByRole("button", { name: "Enregistrer (1)" }));
    const dialog = await screen.findByRole("dialog", { name: "Envoyer 1 mesure ?" });
    expect(within(dialog).getByText("2 sur 10")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Envoyer les mesures" }));
    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalled());
    expect(sentBody().items).toEqual([{ membership_id: 1, attempt_no: 1, count: 2, client_uuid: expect.any(String) }]);
    expect(sentBody().test_id).toBe(2);
  });

  it("saisie libre : valeur décimale envoyée en chaîne, jamais en flottant", async () => {
    const user = userEvent.setup();
    const test = makeTest({ id: 3, name: "Précision de passes", kind: "free", stopwatch_available: false, distance_m: null, unit: "points", unit_label: "points", decimals: 1, higher_is_better: true });
    renderModal([test]);
    await chooseAndStart(user, ["Alice"], "Précision");
    await user.type(screen.getByLabelText("Valeur"), "17,5");
    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([{ membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 1, attempt_no: 1, ...makeValue({ time_ms: null, value: "17.5", display: "17,5 pts", derived: {} }) } }]),
    );
    await user.click(screen.getByRole("button", { name: "Enregistrer (1)" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Envoyer 1 mesure ?" })).getByRole("button", { name: "Envoyer les mesures" }));
    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalled());
    expect(sentBody().items[0]).toMatchObject({ membership_id: 1, value: "17.5" });
  });

  it("abandon coché : envoyé comme « dnf » sans valeur", async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(await screen.findByRole("radio", { name: /Sprint 30 m/ }));
    await user.click(screen.getByRole("button", { name: "Saisie manuelle" }));
    await user.click(await screen.findByRole("checkbox", { name: /Alice/ }));
    await user.click(screen.getByRole("button", { name: "Commencer" }));
    await user.click(screen.getByRole("checkbox", { name: "Abandon de Alice Durand" }));
    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([{ membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 1, attempt_no: 1, ...makeValue({ outcome: "dnf", time_ms: null, display: "Abandon", derived: {} }) } }]),
    );
    await user.click(screen.getByRole("button", { name: "Enregistrer (1)" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Envoyer 1 mesure ?" })).getByRole("button", { name: "Envoyer les mesures" }));
    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalled());
    expect(sentBody().items[0]).toEqual({ membership_id: 1, attempt_no: 1, outcome: "dnf", client_uuid: expect.any(String) });
  });
});

describe("MeasureModal — distance en temps donné", () => {
  it("décompte la durée puis passe à la saisie des distances (tours × longueur + mètres)", async () => {
    const user = userEvent.setup();
    const cooper = makeTest({ id: 4, name: "Cooper", kind: "distance_in_time", distance_m: null, duration_s: 720, unit: "meters", higher_is_better: true });
    renderModal([cooper]);
    await chooseAndStart(user, ["Alice"], "Cooper");
    expect(screen.getByRole("timer")).toHaveTextContent("12:00");
    now = 0;
    await user.click(screen.getByRole("button", { name: "Départ" }));
    now = 1000;
    tick();
    expect(screen.getByRole("timer")).toHaveTextContent("11:59");
    now = 721_000;
    tick();
    expect(await screen.findByText("Temps écoulé. Saisissez la distance de chaque joueur.")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Longueur du tour/), "400");
    await user.type(screen.getByLabelText(/^Tours/), "6");
    await user.type(screen.getByLabelText(/Mètres en plus/), "50");
    vi.mocked(bulkPerformanceResults).mockResolvedValue(
      bulkResponse([{ membership_id: 1, outcome: "created", message: "", warning: "", result: { id: 1, attempt_no: 1, ...makeValue({ time_ms: null, distance_m: "2450.00", display: "2 450 m" }) } }]),
    );
    await user.click(screen.getByRole("button", { name: "Enregistrer (1)" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Envoyer 1 mesure ?" })).getByRole("button", { name: "Envoyer les mesures" }));
    await waitFor(() => expect(bulkPerformanceResults).toHaveBeenCalled());
    expect(sentBody().method).toBe("stopwatch");
    expect(sentBody().items[0]).toMatchObject({ membership_id: 1, distance_m: "2450" });
  });
});
