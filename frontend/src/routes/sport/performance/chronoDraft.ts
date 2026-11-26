/**
 * Sauvegarde locale d'un chrono non enregistré
 * (docs/ecrans/sport-statistiques-seance.md, partie C, cas « Le téléphone
 * s'éteint ») : l'état du chrono est écrit sur le téléphone pendant la mesure
 * et proposé à la réouverture : « Un chrono non enregistré a été retrouvé ».
 *
 * L'horloge du chrono (`performance.now()`) repart de zéro à chaque
 * chargement de la page : les horodatages sont donc convertis en heure
 * réelle (`Date.now()`) à l'écriture, puis reconvertis dans l'horloge de la
 * nouvelle page à la lecture. Un joueur encore « en course » au moment de
 * l'extinction reste en course : son temps inclut l'interruption, au Coach de
 * l'arrêter, de le noter « Abandon » ou de le retirer.
 *
 * Données gardées : identifiants (utilisateur, séance, test, adhésions),
 * temps et étapes. Aucun nom de joueur, aucune donnée médicale. La sauvegarde
 * n'est proposée qu'au même utilisateur, sur la même séance.
 */
import type { PerformanceStartMode } from "../../../api/performance";
import { formatTime } from "../sportTime";
import type { RunnerMap, RunnerState } from "./chronoState";
import type { ValueDraft } from "./ValueInput";

export const CHRONO_DRAFT_KEY = "vesta.performance.chrono-draft";
/**
 * Au-delà, la sauvegarde n'est plus proposée (et elle est effacée) : c'est le
 * délai de mesure d'une séance (48 h, partie C7 règle 2, proposition C-Q8) ;
 * passé ce délai, l'API refuserait de toute façon l'envoi.
 */
export const CHRONO_DRAFT_MAX_AGE_MS = 48 * 60 * 60 * 1000;
/** Fréquence d'écriture pendant la mesure (« toutes les secondes »). */
export const CHRONO_DRAFT_SAVE_INTERVAL_MS = 1000;

const VERSION = 1;

/** État de l'écran « Chronomètre », dans l'horloge monotone de la page. */
export interface StopwatchSnapshot {
  phase: "ready" | "running" | "finished";
  groupStart: number | null;
  runners: RunnerMap;
  rounds: RunnerMap[];
  frozen: number;
}

/** État du compte à rebours (« distance en temps donné »), horloge monotone. */
export interface CountdownSnapshot {
  startedAt: number | null;
  /** Le temps est écoulé : la page en est à la saisie des distances. */
  elapsed: boolean;
  /** Distances déjà saisies après le compte à rebours. */
  entries?: ManualEntries;
}

/** Saisie en cours des distances (C6.3), par adhésion. */
export interface ManualEntries {
  drafts: Record<number, ValueDraft>;
  lapLength: string;
}

export interface ChronoDraftContext {
  userId: number;
  eventId: number;
  testId: number;
  testName: string;
  startMode: PerformanceStartMode;
  playerIds: number[];
}

export type ChronoDraftState =
  | { step: "stopwatch"; stopwatch: StopwatchSnapshot }
  | { step: "countdown"; countdown: CountdownSnapshot };

/** Forme stockée : tous les horodatages sont en heure réelle (ms depuis 1970). */
export type ChronoDraft = ChronoDraftContext & ChronoDraftState & { v: number; savedAt: number };

export interface Clocks {
  /** Horloge monotone de la page (`performance.now()`). */
  mono: number;
  /** Heure réelle (`Date.now()`). */
  wall: number;
}

function shiftRunner(state: RunnerState, delta: number): RunnerState {
  if (state.status === "running") return { status: "running", startedAt: state.startedAt + delta };
  if (state.status === "stopped") return { status: "stopped", startedAt: state.startedAt + delta, timeMs: state.timeMs };
  return state;
}

function shiftMap(map: RunnerMap, delta: number): RunnerMap {
  return Object.fromEntries(Object.entries(map).map(([id, state]) => [id, shiftRunner(state, delta)]));
}

/** Décale tous les horodatages d'un état (passage monotone ↔ heure réelle). */
export function shiftState(state: ChronoDraftState, delta: number): ChronoDraftState {
  if (state.step === "countdown") {
    const { startedAt, ...rest } = state.countdown;
    return { step: "countdown", countdown: { ...rest, startedAt: startedAt === null ? null : startedAt + delta } };
  }
  const s = state.stopwatch;
  return {
    step: "stopwatch",
    stopwatch: {
      phase: s.phase,
      groupStart: s.groupStart === null ? null : s.groupStart + delta,
      runners: shiftMap(s.runners, delta),
      rounds: s.rounds.map((map) => shiftMap(map, delta)),
      frozen: s.frozen,
    },
  };
}

/** Construit la sauvegarde (heure réelle) à partir de l'état courant (horloge monotone). */
export function toDraft(context: ChronoDraftContext, state: ChronoDraftState, clocks: Clocks): ChronoDraft {
  return { v: VERSION, ...context, ...shiftState(state, clocks.wall - clocks.mono), savedAt: clocks.wall };
}

/** Reconvertit une sauvegarde dans l'horloge monotone de la page courante. */
export function fromDraft(draft: ChronoDraft, clocks: Clocks): ChronoDraftState {
  const state: ChronoDraftState =
    draft.step === "countdown"
      ? { step: "countdown", countdown: draft.countdown }
      : { step: "stopwatch", stopwatch: draft.stopwatch };
  return shiftState(state, clocks.mono - clocks.wall);
}

// La sauvegarde vient du stockage du téléphone, modifiable à la main : chaque
// champ est vérifié, et une sauvegarde invalide est effacée sans être proposée.
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const isId = (x: unknown): x is number => Number.isInteger(x) && (x as number) > 0;
const isRecord = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);
const START_MODES: readonly unknown[] = ["group", "individual"] satisfies PerformanceStartMode[];
const PHASES: readonly unknown[] = ["ready", "running", "finished"] satisfies StopwatchSnapshot["phase"][];

function isRunnerState(x: unknown): boolean {
  if (!isRecord(x)) return false;
  switch (x.status) {
    case "running":
      return finite(x.startedAt);
    case "stopped":
      return finite(x.startedAt) && finite(x.timeMs) && x.timeMs >= 0;
    case "idle":
    case "dnf":
    case "removed":
      return true;
    default:
      return false;
  }
}

function isRunnerMap(x: unknown): boolean {
  return isRecord(x) && Object.entries(x).every(([id, state]) => isId(Number(id)) && isRunnerState(state));
}

function isValueDraft(x: unknown): boolean {
  return (
    isRecord(x) &&
    typeof x.text === "string" &&
    typeof x.laps === "string" &&
    typeof x.extra === "string" &&
    typeof x.dnf === "boolean"
  );
}

function isManualEntries(x: unknown): boolean {
  return (
    isRecord(x) &&
    typeof x.lapLength === "string" &&
    isRecord(x.drafts) &&
    Object.entries(x.drafts).every(([id, draft]) => isId(Number(id)) && isValueDraft(draft))
  );
}

function isDraft(value: unknown): value is ChronoDraft {
  if (!isRecord(value)) return false;
  const d = value;
  if (d.v !== VERSION) return false;
  if (!isId(d.userId) || !isId(d.eventId) || !isId(d.testId)) return false;
  if (typeof d.testName !== "string" || !finite(d.savedAt) || !START_MODES.includes(d.startMode)) return false;
  if (!Array.isArray(d.playerIds) || !d.playerIds.every(isId)) return false;
  if (d.step === "stopwatch") {
    const s = d.stopwatch;
    return (
      isRecord(s) &&
      PHASES.includes(s.phase) &&
      (s.groupStart === null || finite(s.groupStart)) &&
      finite(s.frozen) &&
      isRunnerMap(s.runners) &&
      Array.isArray(s.rounds) &&
      s.rounds.every(isRunnerMap)
    );
  }
  if (d.step === "countdown") {
    const c = d.countdown;
    return (
      isRecord(c) &&
      (c.startedAt === null || finite(c.startedAt)) &&
      typeof c.elapsed === "boolean" &&
      (c.entries === undefined || isManualEntries(c.entries))
    );
  }
  return false;
}

/** Une sauvegarde par utilisateur et par séance : un autre chrono ne l'écrase jamais. */
export function chronoDraftKey(userId: number, eventId: number): string {
  return `${CHRONO_DRAFT_KEY}.${userId}.${eventId}`;
}

export function writeChronoDraft(draft: ChronoDraft): void {
  try {
    window.localStorage.setItem(chronoDraftKey(draft.userId, draft.eventId), JSON.stringify(draft));
  } catch {
    // Stockage plein ou indisponible : le chrono continue, sans sauvegarde.
  }
}

export function clearChronoDraft(userId: number, eventId: number): void {
  try {
    window.localStorage.removeItem(chronoDraftKey(userId, eventId));
  } catch {
    // Rien à faire.
  }
}

function draftKeys(): string[] {
  const keys: string[] = [];
  for (let i = 0; i < window.localStorage.length; i += 1) {
    const key = window.localStorage.key(i);
    if (key !== null && key.startsWith(`${CHRONO_DRAFT_KEY}.`)) keys.push(key);
  }
  return keys;
}

/** À la déconnexion : aucune sauvegarde ne reste sur un téléphone qui peut être partagé. */
export function clearAllChronoDrafts(): void {
  try {
    for (const key of draftKeys()) window.localStorage.removeItem(key);
  } catch {
    // Rien à faire.
  }
}

/** Efface les sauvegardes illisibles ou trop anciennes (toutes séances et utilisateurs). */
export function purgeExpiredChronoDrafts(now: number = Date.now()): void {
  try {
    for (const key of draftKeys()) {
      let keep = false;
      try {
        const parsed: unknown = JSON.parse(window.localStorage.getItem(key) ?? "null");
        keep = isDraft(parsed) && Math.abs(now - parsed.savedAt) <= CHRONO_DRAFT_MAX_AGE_MS;
      } catch {
        keep = false;
      }
      if (!keep) window.localStorage.removeItem(key);
    }
  } catch {
    // Stockage indisponible : rien à purger.
  }
}

/**
 * Sauvegarde proposée à cet utilisateur pour cette séance, ou `null`.
 * Une sauvegarde illisible, incohérente ou trop ancienne est effacée.
 */
export function readChronoDraft(userId: number, eventId: number, now: number = Date.now()): ChronoDraft | null {
  let parsed: unknown;
  try {
    const raw = window.localStorage.getItem(chronoDraftKey(userId, eventId));
    if (!raw) return null;
    parsed = JSON.parse(raw);
  } catch {
    clearChronoDraft(userId, eventId);
    return null;
  }
  if (
    !isDraft(parsed) ||
    parsed.userId !== userId ||
    parsed.eventId !== eventId ||
    Math.abs(now - parsed.savedAt) > CHRONO_DRAFT_MAX_AGE_MS
  ) {
    clearChronoDraft(userId, eventId);
    return null;
  }
  return parsed;
}

/** Faut-il sauvegarder cet état ? Rien tant qu'aucun chrono n'a commencé. */
export function isWorthSaving(state: ChronoDraftState): boolean {
  if (state.step === "countdown") return state.countdown.startedAt !== null || state.countdown.elapsed;
  const s = state.stopwatch;
  return s.phase !== "ready" || s.rounds.length > 0 || Object.values(s.runners).some((r) => r.status !== "idle");
}

/** « 14:32 » : heure de la dernière sauvegarde, pour le message de reprise. */
export function formatDraftTime(savedAt: number): string {
  return formatTime(new Date(savedAt).toISOString());
}
