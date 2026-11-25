import { useEffect, useState } from "react";
import { useDelayedVisible } from "../../hooks/useDelayedVisible";
import { Button } from "./Button";
import { Skeleton, type SkeletonVariant } from "./Skeleton";

const SLOW_THRESHOLD_MS = 10_000;

export interface LoaderProps {
  loading: boolean;
  /** Pleine page (titre + contexte + cartes) ou liste de squelettes. */
  variant?: "page" | "list";
  /** Variante de squelette pour `variant="list"` (3.5). */
  listSkeleton?: SkeletonVariant;
  /** Nombre de lignes pour `variant="list"`. */
  count?: number;
  /** Rappelé quand le chargement dépasse 10 s et que l'utilisateur relance. */
  onRetry?: () => void;
  className?: string;
}

/**
 * Retour visuel de chargement (docs/lot0/design-system.md §3.5) : aucune
 * page ni action sans indicateur. N'apparaît qu'après 200 ms, reste au
 * moins 300 ms, signale un chargement anormalement long après 10 s.
 */
export function Loader({
  loading,
  variant = "list",
  listSkeleton = "row",
  count = 5,
  onRetry,
  className = "",
}: LoaderProps) {
  const visible = useDelayedVisible(loading);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!loading) {
      setSlow(false);
      return;
    }
    const timer = window.setTimeout(() => setSlow(true), SLOW_THRESHOLD_MS);
    return () => window.clearTimeout(timer);
  }, [loading]);

  if (!visible) return null;

  if (slow) {
    return (
      <div
        role="status"
        aria-live="polite"
        className={["flex flex-col items-center gap-2 py-6 text-center", className].join(" ")}
      >
        <p className="text-sm text-text-muted">
          Le chargement prend plus de temps que prévu.
        </p>
        {onRetry ? (
          <Button size="sm" variant="secondary" onClick={onRetry}>
            Réessayer
          </Button>
        ) : null}
      </div>
    );
  }

  if (variant === "page") {
    return (
      <div aria-busy="true" aria-live="polite" className={["space-y-6", className].join(" ")}>
        <span className="sr-only">Chargement…</span>
        <div className="h-[3px] w-full overflow-hidden rounded-full bg-surface-muted">
          <div className="h-full w-1/3 rounded-full bg-primary motion-safe:animate-progress-indeterminate" />
        </div>
        <div className="space-y-2">
          <Skeleton variant="row" className="max-w-xs" />
          <div className="h-3 w-40 rounded bg-skeleton motion-safe:animate-skeleton" />
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Skeleton variant="card" />
          <Skeleton variant="card" />
        </div>
      </div>
    );
  }

  return (
    <div
      aria-busy="true"
      aria-live="polite"
      className={["space-y-3", className].join(" ")}
    >
      <span className="sr-only">Chargement…</span>
      {Array.from({ length: count }, (_, index) => (
        <Skeleton key={index} variant={listSkeleton} />
      ))}
    </div>
  );
}
