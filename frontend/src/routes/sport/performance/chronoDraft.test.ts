import { beforeEach, describe, expect, it } from "vitest";
import {
  CHRONO_DRAFT_MAX_AGE_MS,
  chronoDraftKey,
  clearAllChronoDrafts,
  clearChronoDraft,
  purgeExpiredChronoDrafts,
  fromDraft,
  isWorthSaving,
  readChronoDraft,
  toDraft,
  writeChronoDraft,
  type ChronoDraftContext,
  type ChronoDraftState,
} from "./chronoDraft";

const CONTEXT: ChronoDraftContext = {
  userId: 5,
  eventId: 7,
  testId: 1,
  testName: "Sprint 30 m",
  startMode: "group",
  playerIds: [1, 2, 3],
};

const RUNNING: ChronoDraftState = {
  step: "stopwatch",
  stopwatch: {
    phase: "running",
    groupStart: 1000,
    runners: {
      1: { status: "stopped", startedAt: 1000, timeMs: 4370 },
      2: { status: "running", startedAt: 1000 },
      3: { status: "dnf" },
    },
    rounds: [{ 1: { status: "stopped", startedAt: 200, timeMs: 4500 } }],
    frozen: 0,
  },
};

beforeEach(() => window.localStorage.clear());

describe("chronoDraft — conversion des horloges", () => {
  it("stocke l'heure réelle puis la reconvertit dans l'horloge d'une nouvelle page", () => {
    // Page 1 : horloge monotone à 5 370 ms, heure réelle 1 000 000 ms.
    const draft = toDraft(CONTEXT, RUNNING, { mono: 5370, wall: 1_000_000 });
    expect(draft.savedAt).toBe(1_000_000);
    expect(draft.step === "stopwatch" && draft.stopwatch.groupStart).toBe(1_000_000 - 4370);

    // Page 2, après redémarrage : l'horloge monotone repart de 50 ; 60 s réelles ont passé.
    const back = fromDraft(draft, { mono: 50, wall: 1_060_000 });
    if (back.step !== "stopwatch") throw new Error("état inattendu");
    const runner = back.stopwatch.runners[2]!;
    if (runner.status !== "running") throw new Error("état inattendu");
    // Le joueur encore en course a couru 4,37 s + 60 s d'interruption.
    expect(50 - runner.startedAt).toBe(4370 + 60_000);
    // Les temps déjà pris ne changent jamais.
    expect(back.stopwatch.runners[1]).toEqual({ status: "stopped", startedAt: runner.startedAt, timeMs: 4370 });
    expect(back.stopwatch.runners[3]).toEqual({ status: "dnf" });
    expect(back.stopwatch.rounds[0]![1]).toMatchObject({ status: "stopped", timeMs: 4500 });
  });

  it("compte à rebours : le départ est conservé, ainsi que « temps écoulé »", () => {
    const state: ChronoDraftState = { step: "countdown", countdown: { startedAt: 2000, elapsed: true } };
    const back = fromDraft(toDraft(CONTEXT, state, { mono: 3000, wall: 10_000 }), { mono: 0, wall: 10_000 });
    expect(back).toEqual({ step: "countdown", countdown: { startedAt: -1000, elapsed: true } });
  });
});

describe("chronoDraft — stockage", () => {
  it("une sauvegarde par utilisateur et par séance", () => {
    writeChronoDraft(toDraft(CONTEXT, RUNNING, { mono: 0, wall: 1000 }));
    writeChronoDraft(toDraft({ ...CONTEXT, eventId: 8 }, RUNNING, { mono: 0, wall: 1000 }));
    expect(window.localStorage.getItem(chronoDraftKey(5, 7))).not.toBeNull();
    expect(readChronoDraft(5, 7, 1000)?.eventId).toBe(7);
    expect(readChronoDraft(5, 8, 1000)?.eventId).toBe(8);
    // Un autre utilisateur du même téléphone ne voit rien.
    expect(readChronoDraft(6, 7, 1000)).toBeNull();
    clearChronoDraft(5, 7);
    expect(readChronoDraft(5, 7, 1000)).toBeNull();
    expect(readChronoDraft(5, 8, 1000)).not.toBeNull();
  });

  it("efface une sauvegarde trop ancienne", () => {
    writeChronoDraft(toDraft(CONTEXT, RUNNING, { mono: 0, wall: 1000 }));
    expect(readChronoDraft(5, 7, 1000 + CHRONO_DRAFT_MAX_AGE_MS + 1)).toBeNull();
    expect(window.localStorage.getItem(chronoDraftKey(5, 7))).toBeNull();
  });

  it("efface une sauvegarde illisible ou d'un format inconnu", () => {
    window.localStorage.setItem(chronoDraftKey(5, 7), "{pas du json");
    expect(readChronoDraft(5, 7)).toBeNull();
    expect(window.localStorage.getItem(chronoDraftKey(5, 7))).toBeNull();

    window.localStorage.setItem(chronoDraftKey(5, 7), JSON.stringify({ v: 99, userId: 5, eventId: 7 }));
    expect(readChronoDraft(5, 7)).toBeNull();
    expect(window.localStorage.getItem(chronoDraftKey(5, 7))).toBeNull();
  });

  it("ne garde que des identifiants, des temps et le nom du test (aucun nom de joueur)", () => {
    writeChronoDraft(toDraft(CONTEXT, RUNNING, { mono: 0, wall: 1000 }));
    const stored = JSON.parse(window.localStorage.getItem(chronoDraftKey(5, 7)) ?? "{}") as Record<string, unknown>;
    expect(Object.keys(stored).sort()).toEqual(
      ["eventId", "playerIds", "savedAt", "startMode", "step", "stopwatch", "testId", "testName", "userId", "v"].sort(),
    );
  });
});

describe("chronoDraft — sauvegarde modifiée à la main", () => {
  function tamper(patch: (draft: Record<string, unknown>) => void) {
    writeChronoDraft(toDraft(CONTEXT, RUNNING, { mono: 0, wall: 1000 }));
    const stored = JSON.parse(window.localStorage.getItem(chronoDraftKey(5, 7))!) as Record<string, unknown>;
    patch(stored);
    window.localStorage.setItem(chronoDraftKey(5, 7), JSON.stringify(stored));
  }

  it.each([
    ["un état de coureur inconnu", (d: Record<string, unknown>) => ((d.stopwatch as { runners: Record<string, unknown> }).runners[2] = { status: "envolé" })],
    ["un temps qui n'est pas un nombre", (d: Record<string, unknown>) => ((d.stopwatch as { runners: Record<string, unknown> }).runners[1] = { status: "stopped", startedAt: 0, timeMs: "vite" })],
    ["un mode de départ inconnu", (d: Record<string, unknown>) => (d.startMode = "relais")],
    ["une phase inconnue", (d: Record<string, unknown>) => ((d.stopwatch as Record<string, unknown>).phase = "pause")],
    ["un joueur sans identifiant valide", (d: Record<string, unknown>) => (d.playerIds = [1, "deux"])],
    ["un identifiant de séance négatif", (d: Record<string, unknown>) => (d.eventId = -7)],
  ])("efface une sauvegarde avec %s", (_label, patch) => {
    tamper(patch);
    expect(readChronoDraft(5, 7, 1000)).toBeNull();
    expect(window.localStorage.getItem(chronoDraftKey(5, 7))).toBeNull();
  });

  it("garde les distances saisies après le compte à rebours, et les vérifie", () => {
    const entries = { drafts: { 1: { text: "2450", laps: "", extra: "", dnf: false } }, lapLength: "400" };
    const state: ChronoDraftState = { step: "countdown", countdown: { startedAt: 10, elapsed: true, entries } };
    writeChronoDraft(toDraft(CONTEXT, state, { mono: 0, wall: 1000 }));
    const read = readChronoDraft(5, 7, 1000)!;
    expect(fromDraft(read, { mono: 0, wall: 1000 })).toEqual(state);

    tamper((d) => {
      d.step = "countdown";
      d.countdown = { startedAt: 10, elapsed: true, entries: { drafts: { 1: { text: 2450 } }, lapLength: "400" } };
    });
    expect(readChronoDraft(5, 7, 1000)).toBeNull();
  });
});

describe("chronoDraft — ménage", () => {
  it("à la déconnexion, efface toutes les sauvegardes du chrono et rien d'autre", () => {
    writeChronoDraft(toDraft(CONTEXT, RUNNING, { mono: 0, wall: 1000 }));
    writeChronoDraft(toDraft({ ...CONTEXT, userId: 6, eventId: 8 }, RUNNING, { mono: 0, wall: 1000 }));
    window.localStorage.setItem("vesta.autre", "garder");
    clearAllChronoDrafts();
    expect(window.localStorage.getItem(chronoDraftKey(5, 7))).toBeNull();
    expect(window.localStorage.getItem(chronoDraftKey(6, 8))).toBeNull();
    expect(window.localStorage.getItem("vesta.autre")).toBe("garder");
  });

  it("efface les sauvegardes trop anciennes ou illisibles de toutes les séances", () => {
    writeChronoDraft(toDraft(CONTEXT, RUNNING, { mono: 0, wall: 1000 }));
    writeChronoDraft(toDraft({ ...CONTEXT, eventId: 8 }, RUNNING, { mono: 0, wall: 1000 + CHRONO_DRAFT_MAX_AGE_MS }));
    window.localStorage.setItem(chronoDraftKey(6, 9), "{illisible");
    purgeExpiredChronoDrafts(1000 + CHRONO_DRAFT_MAX_AGE_MS + 1);
    expect(window.localStorage.getItem(chronoDraftKey(5, 7))).toBeNull();
    expect(window.localStorage.getItem(chronoDraftKey(5, 8))).not.toBeNull();
    expect(window.localStorage.getItem(chronoDraftKey(6, 9))).toBeNull();
  });
});

describe("chronoDraft — isWorthSaving", () => {
  it("rien à sauvegarder avant le premier départ", () => {
    expect(
      isWorthSaving({ step: "stopwatch", stopwatch: { phase: "ready", groupStart: null, runners: { 1: { status: "idle" } }, rounds: [], frozen: 0 } }),
    ).toBe(false);
    expect(isWorthSaving({ step: "countdown", countdown: { startedAt: null, elapsed: false } })).toBe(false);
    expect(isWorthSaving(RUNNING)).toBe(true);
    expect(isWorthSaving({ step: "countdown", countdown: { startedAt: 10, elapsed: false } })).toBe(true);
  });
});
