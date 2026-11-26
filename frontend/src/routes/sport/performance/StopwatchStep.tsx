import { useEffect, useMemo, useState } from "react";
import type { PerformanceStartMode, PerformanceTest, PlayerBrief } from "../../../api/performance";
import { Avatar, Banner, Button, ConfirmDialog } from "../../../design-system";
import {
  IDLE,
  allSettled,
  initialMap,
  resumeRunner,
  startRunner,
  stopRunner,
  type RunnerMap,
  type RunnerState,
} from "./chronoState";
import type { StopwatchSnapshot } from "./chronoDraft";
import type { DraftItem } from "./measureTypes";
import { describeFields, formatStopwatch, formatTimeMs, indicativeSpeedKmh } from "./performanceFormat";
import { StepFooter } from "./StepFooter";
import { monotonicClock, useTicker, type Clock } from "./useTicker";
import { useWakeLock } from "./useWakeLock";

type Phase = "ready" | "running" | "finished";

export interface StopwatchStepProps {
  test: PerformanceTest;
  players: PlayerBrief[];
  startMode: PerformanceStartMode;
  /** Horloge monotone (`performance.now()`), injectable pour les tests. */
  clock?: Clock;
  onDirtyChange: (dirty: boolean) => void;
  /** Le Coach demande l'envoi : le parent affiche le récapitulatif de confirmation. */
  onReview: (items: DraftItem[]) => void;
  /** État restauré d'une sauvegarde locale (horloge monotone de la page). */
  initial?: StopwatchSnapshot;
  /** Reçoit l'état à chaque changement, pour la sauvegarde locale. */
  onSnapshot?: (snapshot: StopwatchSnapshot) => void;
}

/** Garde seulement les joueurs encore à l'écran (une sauvegarde peut en citer d'autres). */
function pick(map: RunnerMap, ids: number[]): RunnerMap {
  const kept: RunnerMap = {};
  for (const id of ids) {
    const state = map[id];
    if (state !== undefined) kept[id] = state;
  }
  return kept;
}

function stateOf(map: RunnerMap, id: number): RunnerState {
  return map[id] ?? IDLE;
}

function itemsOf(test: PerformanceTest, players: PlayerBrief[], map: RunnerMap, attemptNo: number): DraftItem[] {
  const items: DraftItem[] = [];
  for (const player of players) {
    const state = stateOf(map, player.membership_id);
    if (state.status === "stopped") {
      items.push({
        membershipId: player.membership_id,
        name: player.name,
        attemptNo,
        fields: { time_ms: state.timeMs },
        label: describeFields(test, { time_ms: state.timeMs }),
      });
    } else if (state.status === "dnf") {
      items.push({
        membershipId: player.membership_id,
        name: player.name,
        attemptNo,
        fields: { outcome: "dnf" },
        label: "Abandon",
      });
    }
  }
  return items;
}

/**
 * Chrono dans l'application (docs/ecrans/sport-statistiques-seance.md C6.2).
 * Le temps de chaque joueur est l'écart entre deux lectures de l'horloge
 * monotone, en millisecondes entières : exact même si l'écran se met en
 * veille. Les lignes ne changent jamais de place pendant le chrono.
 */
export function StopwatchStep({
  test,
  players,
  startMode,
  clock = monotonicClock,
  onDirtyChange,
  onReview,
  initial,
  onSnapshot,
}: StopwatchStepProps) {
  const ids = useMemo(() => players.map((p) => p.membership_id), [players]);
  const [runners, setRunners] = useState<RunnerMap>(() =>
    initial ? { ...initialMap(ids), ...pick(initial.runners, ids) } : initialMap(ids),
  );
  const [rounds, setRounds] = useState<RunnerMap[]>(() => initial?.rounds.map((map) => pick(map, ids)) ?? []);
  const [phase, setPhase] = useState<Phase>(() => initial?.phase ?? "ready");
  const [groupStart, setGroupStart] = useState<number | null>(() => initial?.groupStart ?? null);
  const [frozen, setFrozen] = useState(() => initial?.frozen ?? 0);
  const [menuFor, setMenuFor] = useState<number | null>(null);
  const [confirmStop, setConfirmStop] = useState(false);

  useTicker(phase === "running");
  const { held } = useWakeLock(phase === "running");

  useEffect(() => {
    onSnapshot?.({ phase, groupStart, runners, rounds, frozen });
  }, [phase, groupStart, runners, rounds, frozen, onSnapshot]);

  const dirty = rounds.length > 0 || phase !== "ready" || ids.some((id) => stateOf(runners, id).status !== "idle");
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  const total = ids.filter((id) => stateOf(runners, id).status !== "removed").length;
  const settled = ids.filter((id) => ["stopped", "dnf"].includes(stateOf(runners, id).status)).length;
  const running = ids.filter((id) => stateOf(runners, id).status === "running");
  const attemptNo = rounds.length + 1;

  function commit(next: RunnerMap, now: number) {
    setRunners(next);
    if (phase !== "ready" && allSettled(next, ids)) {
      const times = ids.flatMap((id) => {
        const state = stateOf(next, id);
        return state.status === "stopped" ? [state.timeMs] : [];
      });
      setFrozen(times.length > 0 ? Math.max(...times) : groupStart === null ? 0 : Math.round(now - groupStart));
      setPhase("finished");
    }
  }

  function startGroup() {
    const now = clock();
    const next: RunnerMap = {};
    for (const id of ids) next[id] = startRunner(stateOf(runners, id), now);
    setRunners(next);
    setGroupStart(now);
    setPhase("running");
  }

  function startOne(id: number) {
    const now = clock();
    setRunners({ ...runners, [id]: startRunner(stateOf(runners, id), now) });
    if (phase === "ready") setPhase("running");
  }

  function stopOne(id: number) {
    const now = clock();
    commit({ ...runners, [id]: stopRunner(stateOf(runners, id), now) }, now);
  }

  /** Un joueur remis en jeu pendant un départ groupé repart du chrono commun. */
  function revived(): RunnerState {
    return startMode === "group" && phase === "running" && groupStart !== null
      ? { status: "running", startedAt: groupStart }
      : IDLE;
  }

  function resumeOne(id: number) {
    const state = stateOf(runners, id);
    setRunners({ ...runners, [id]: state.status === "dnf" ? revived() : resumeRunner(state) });
  }

  function setStatus(id: number, state: RunnerState) {
    setMenuFor(null);
    const next = { ...runners, [id]: state };
    if (phase === "ready") setRunners(next);
    else commit(next, clock());
  }

  function finishNow() {
    const now = clock();
    const next: RunnerMap = { ...runners };
    for (const id of ids) {
      const state = stateOf(runners, id);
      if (state.status === "running") next[id] = { status: "dnf" };
      else if (state.status === "idle") next[id] = { status: "removed" };
    }
    setConfirmStop(false);
    setRunners(next);
    const times = ids.flatMap((id) => {
      const state = stateOf(next, id);
      return state.status === "stopped" ? [state.timeMs] : [];
    });
    setFrozen(times.length > 0 ? Math.max(...times) : groupStart === null ? 0 : Math.round(now - groupStart));
    setPhase("finished");
  }

  function requestFinish() {
    if (running.length > 0) setConfirmStop(true);
    else finishNow();
  }

  function newAttempt() {
    setRounds([...rounds, runners]);
    setRunners(initialMap(ids));
    setPhase("ready");
    setGroupStart(null);
    setFrozen(0);
    setMenuFor(null);
  }

  const items = [
    ...rounds.flatMap((map, index) => itemsOf(test, players, map, index + 1)),
    ...(phase === "finished" ? itemsOf(test, players, runners, attemptNo) : []),
  ];

  // Chrono commun affiché en grand.
  const now = clock();
  let shown = 0;
  if (phase === "finished") shown = frozen;
  else if (startMode === "group") shown = groupStart === null ? 0 : Math.max(0, now - groupStart);
  else {
    const first = running[0];
    const state = first === undefined ? IDLE : stateOf(runners, first);
    shown = state.status === "running" ? Math.max(0, now - state.startedAt) : frozen;
  }

  const activeIndividual = startMode === "individual" && running.length === 0 && phase !== "finished"
    ? ids.find((id) => stateOf(runners, id).status === "idle")
    : undefined;

  let caption = `Prêt · ${total} joueur${total > 1 ? "s" : ""}`;
  if (phase === "running") caption = `Chrono en cours · ${settled} sur ${total}`;
  if (phase === "finished") caption = "Chrono terminé";

  return (
    <div className="space-y-3">
      <div className="text-center">
        <p
          className="text-2xl font-bold tabular-nums text-text"
          role="timer"
        >
          {formatStopwatch(shown)}
        </p>
        <p className="text-sm text-text">{caption}</p>
        <p className="text-xs text-text-muted">
          Chronométrage manuel : comptez environ 0,2 s d'écart selon la réaction de la personne qui arrête.
        </p>
      </div>

      {phase === "running" && !held ? <Banner variant="info">Gardez l'écran allumé pendant le chrono.</Banner> : null}

      <ul className="divide-y divide-border rounded-md border border-border">
        {players.map((player) => {
          const id = player.membership_id;
          const state = stateOf(runners, id);
          const canStop = state.status === "running";
          const canStartHere = activeIndividual === id;
          const speed =
            state.status === "stopped" ? indicativeSpeedKmh(test.distance_m, state.timeMs) : null;
          return (
            <li key={id}>
              <div className="relative flex min-h-16 items-center gap-2 px-2">
                <button
                  type="button"
                  aria-label={`Options pour ${player.name}`}
                  aria-expanded={menuFor === id}
                  onClick={() => setMenuFor(menuFor === id ? null : id)}
                  className="relative z-10 shrink-0 rounded-full"
                >
                  <Avatar name={player.name} photoUrl={player.photo} size={32} />
                </button>
                <span className="min-w-0 flex-1">
                  <span className="block break-words text-sm font-medium text-text">{player.name}</span>
                  {player.jersey_number !== null ? (
                    <span className="block text-xs text-text-muted">n°{player.jersey_number}</span>
                  ) : null}
                </span>

                {canStop ? (
                  <button
                    type="button"
                    aria-label={`Arrêter ${player.name}`}
                    onClick={() => stopOne(id)}
                    className="absolute inset-0 flex items-center justify-end bg-status-danger-bg/30 pr-3 text-base font-semibold text-status-danger-fg"
                  >
                    Arrêter
                  </button>
                ) : null}
                {canStartHere ? (
                  <button
                    type="button"
                    aria-label={`Départ de ${player.name}`}
                    onClick={() => startOne(id)}
                    className="absolute inset-0 flex items-center justify-end pr-3 text-base font-semibold text-primary-text"
                  >
                    Départ
                  </button>
                ) : null}
                {state.status === "idle" && !canStartHere ? (
                  <span className="shrink-0 text-xs text-text-muted">{startMode === "group" ? "Prêt" : "En attente"}</span>
                ) : null}
                {state.status === "stopped" ? (
                  <span className="relative z-10 flex shrink-0 items-center gap-1">
                    <span className="text-right">
                      <span className="block text-base font-bold tabular-nums text-text">{formatTimeMs(state.timeMs)}</span>
                      {speed ? <span className="block text-xs text-text-muted">{speed} (indicatif)</span> : null}
                    </span>
                    {phase === "running" ? (
                      <button
                        type="button"
                        aria-label={`Reprendre le chrono de ${player.name}`}
                        onClick={() => resumeOne(id)}
                        className="h-11 w-11 rounded-md text-lg text-text"
                      >
                        ↺
                      </button>
                    ) : null}
                  </span>
                ) : null}
                {state.status === "dnf" ? (
                  <span className="relative z-10 flex shrink-0 items-center gap-1">
                    <span className="text-base font-semibold text-text-muted">Abandon</span>
                    {phase === "running" ? (
                      <button
                        type="button"
                        aria-label={`Reprendre le chrono de ${player.name}`}
                        onClick={() => resumeOne(id)}
                        className="h-11 w-11 rounded-md text-lg text-text"
                      >
                        ↺
                      </button>
                    ) : null}
                  </span>
                ) : null}
                {state.status === "removed" ? (
                  <span className="relative z-10 flex shrink-0 items-center gap-2">
                    <span className="text-xs text-text-muted">Retiré de ce départ</span>
                    {phase !== "finished" ? (
                      <Button size="sm" variant="ghost" onClick={() => setStatus(id, revived())}>
                        Remettre
                      </Button>
                    ) : null}
                  </span>
                ) : null}
              </div>
              {menuFor === id ? (
                <div className="flex flex-wrap gap-2 bg-surface-muted px-3 py-2">
                  <Button size="sm" variant="secondary" onClick={() => setStatus(id, { status: "dnf" })}>
                    Abandon
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setStatus(id, { status: "removed" })}>
                    Retirer de ce départ
                  </Button>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      <StepFooter>
        {phase === "ready" && startMode === "group" ? (
          <Button variant="primary" className="w-full" onClick={startGroup} disabled={total === 0}>
            Départ
          </Button>
        ) : null}
        {phase === "ready" && startMode === "individual" ? (
          <p className="flex-1 text-sm text-text-muted">Appuyez sur « Départ » sur la ligne du joueur actif.</p>
        ) : null}
        {phase === "running" ? (
          <Button className="w-full" variant="secondary" onClick={requestFinish}>
            Terminer
          </Button>
        ) : null}
        {phase === "finished" ? (
          <>
            <Button variant="secondary" className="flex-1" onClick={newAttempt}>
              Nouvel essai
            </Button>
            <Button variant="primary" className="flex-1" disabled={items.length === 0} onClick={() => onReview(items)}>
              Envoyer les mesures ({items.length})
            </Button>
          </>
        ) : null}
      </StepFooter>

      <ConfirmDialog
        open={confirmStop}
        title="Arrêter le chrono ?"
        description={`${running.length} joueur${running.length > 1 ? "s n'ont" : " n'a"} pas été arrêté${running.length > 1 ? "s" : ""} : ${running.length > 1 ? "ils seront notés" : "il sera noté"} « Abandon ».`}
        confirmLabel="Arrêter"
        cancelLabel="Continuer le chrono"
        onConfirm={finishNow}
        onCancel={() => setConfirmStop(false)}
      />
    </div>
  );
}
