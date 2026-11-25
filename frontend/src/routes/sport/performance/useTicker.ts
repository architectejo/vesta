import { useEffect, useState } from "react";

/**
 * Rafraîchit l'affichage du chrono (≈ 10 fois par seconde) tant que `active`.
 * Le temps lui-même n'est jamais compté ici : il se déduit de l'horloge
 * monotone, donc reste exact même si l'écran se met en veille.
 */
export function useTicker(active: boolean, intervalMs = 100): void {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!active) return undefined;
    if (typeof requestAnimationFrame !== "function") {
      const timer = window.setInterval(() => setTick((n) => n + 1), intervalMs);
      return () => window.clearInterval(timer);
    }
    let frame = 0;
    let last = 0;
    let stopped = false;
    const loop = (time: number) => {
      if (stopped) return;
      if (time - last >= intervalMs) {
        last = time;
        setTick((n) => n + 1);
      }
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
    };
  }, [active, intervalMs]);
}

/** Horloge monotone injectable (tests). */
export type Clock = () => number;
export const monotonicClock: Clock = () => performance.now();
