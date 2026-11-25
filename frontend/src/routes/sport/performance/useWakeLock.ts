import { useEffect, useState } from "react";

interface WakeLockSentinelLike {
  release: () => Promise<void>;
  addEventListener?: (type: "release", listener: () => void) => void;
}
interface WakeLockNavigator {
  wakeLock?: { request: (type: "screen") => Promise<WakeLockSentinelLike> };
}

/**
 * Garde l'écran allumé pendant le chrono (Wake Lock). Repli silencieux si le
 * navigateur ne le permet pas : `held` reste faux et l'écran affiche alors un
 * bandeau « Gardez l'écran allumé ». Le verrou est redemandé au retour sur
 * l'onglet (le navigateur le libère quand la page passe en arrière-plan).
 */
export function useWakeLock(active: boolean): { held: boolean } {
  const [held, setHeld] = useState(false);

  useEffect(() => {
    if (!active) return undefined;
    const api = (navigator as unknown as WakeLockNavigator).wakeLock;
    if (!api) return undefined;
    let sentinel: WakeLockSentinelLike | null = null;
    let cancelled = false;

    const acquire = () => {
      api
        .request("screen")
        .then((lock) => {
          if (cancelled) {
            void lock.release().catch(() => undefined);
            return;
          }
          sentinel = lock;
          setHeld(true);
          lock.addEventListener?.("release", () => {
            if (!cancelled) setHeld(false);
          });
        })
        .catch(() => {
          if (!cancelled) setHeld(false);
        });
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") acquire();
    };
    acquire();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
      void sentinel?.release().catch(() => undefined);
      setHeld(false);
    };
  }, [active]);

  return { held };
}
