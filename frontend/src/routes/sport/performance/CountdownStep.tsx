import { useEffect, useRef, useState } from "react";
import type { PerformanceTest } from "../../../api/performance";
import { Banner, Button } from "../../../design-system";
import { StepFooter } from "./StepFooter";
import { monotonicClock, useTicker, type Clock } from "./useTicker";
import { useWakeLock } from "./useWakeLock";

function formatCountdown(ms: number): string {
  const totalSeconds = Math.ceil(Math.max(0, ms) / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export interface CountdownStepProps {
  test: PerformanceTest;
  clock?: Clock;
  /** Appelé quand le temps est écoulé (ou « Terminer maintenant ») : passage à la saisie des distances. */
  onElapsed: () => void;
  onDirtyChange: (dirty: boolean) => void;
  /** Départ restauré d'une sauvegarde locale (horloge monotone de la page). */
  initialStartedAt?: number | null;
  /** Reçoit l'instant du départ, pour la sauvegarde locale. */
  onStarted?: (startedAt: number) => void;
}

/**
 * « Distance en temps donné » (Cooper) : le chrono décompte la durée du test,
 * sans arrêt par joueur ; à zéro, on passe à la saisie de la distance.
 */
export function CountdownStep({
  test,
  clock = monotonicClock,
  onElapsed,
  onDirtyChange,
  initialStartedAt = null,
  onStarted,
}: CountdownStepProps) {
  const [startedAt, setStartedAt] = useState<number | null>(initialStartedAt);
  const firedRef = useRef(false);
  const total = (test.duration_s ?? 0) * 1000;
  const running = startedAt !== null;
  useTicker(running);
  const { held } = useWakeLock(running);

  const remaining = startedAt === null ? total : total - (clock() - startedAt);

  useEffect(() => {
    onDirtyChange(running);
  }, [running, onDirtyChange]);

  useEffect(() => {
    if (running && remaining <= 0 && !firedRef.current) {
      firedRef.current = true;
      onElapsed();
    }
  });

  return (
    <div className="space-y-3">
      <div className="text-center">
        <p role="timer" className="text-2xl font-bold tabular-nums text-text">
          {formatCountdown(remaining)}
        </p>
        <p className="text-sm text-text">{running ? "Compte à rebours en cours" : "Prêt à lancer le compte à rebours"}</p>
      </div>
      {running && !held ? <Banner variant="info">Gardez l'écran allumé pendant le chrono.</Banner> : null}
      <StepFooter>
        {running ? (
          <Button
            className="w-full"
            variant="secondary"
            onClick={() => {
              firedRef.current = true;
              onElapsed();
            }}
          >
            Terminer maintenant
          </Button>
        ) : (
          <Button variant="primary" className="w-full" onClick={() => {
              const now = clock();
              setStartedAt(now);
              onStarted?.(now);
            }}
          >
            Départ
          </Button>
        )}
      </StepFooter>
    </div>
  );
}
