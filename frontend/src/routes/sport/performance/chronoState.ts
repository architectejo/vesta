/**
 * États du chrono d'un joueur. Fonctions pures : l'horloge (`now`, en
 * millisecondes monotones, `performance.now()`) est toujours fournie par
 * l'appelant, jamais lue ici. Le temps d'un joueur = écart entre deux
 * horodatages, arrondi à la milliseconde ENTIÈRE.
 */

export type RunnerState =
  | { status: "idle" }
  | { status: "running"; startedAt: number }
  | { status: "stopped"; startedAt: number; timeMs: number }
  | { status: "dnf" }
  | { status: "removed" };

export type RunnerMap = Record<number, RunnerState>;

export const IDLE: RunnerState = { status: "idle" };

export function elapsedMs(startedAt: number, now: number): number {
  return Math.max(1, Math.round(now - startedAt));
}

export function startRunner(state: RunnerState, now: number): RunnerState {
  return state.status === "idle" ? { status: "running", startedAt: now } : state;
}

export function stopRunner(state: RunnerState, now: number): RunnerState {
  return state.status === "running"
    ? { status: "stopped", startedAt: state.startedAt, timeMs: elapsedMs(state.startedAt, now) }
    : state;
}

/** Annule un arrêt par erreur : le temps repart du chrono d'origine. */
export function resumeRunner(state: RunnerState): RunnerState {
  if (state.status === "stopped") return { status: "running", startedAt: state.startedAt };
  if (state.status === "dnf") return { status: "idle" };
  return state;
}

export function isSettled(state: RunnerState): boolean {
  return state.status === "stopped" || state.status === "dnf" || state.status === "removed";
}

export function allSettled(map: RunnerMap, ids: number[]): boolean {
  return ids.length > 0 && ids.every((id) => isSettled(map[id] ?? IDLE));
}

export function initialMap(ids: number[]): RunnerMap {
  return Object.fromEntries(ids.map((id) => [id, IDLE]));
}
