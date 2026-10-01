// Réutilise la découpe de carte de joueur (A7 : « la même silhouette »)
// sans dupliquer le clip-path.
import "./PlayerTradingCard.css";

export type SkeletonVariant = "row" | "table-row" | "card" | "kpi" | "pitch" | "player-card";

export interface SkeletonProps {
  variant?: SkeletonVariant;
  className?: string;
}

/**
 * Bloc gris animé (docs/lot0/design-system.md §3.5). Statique si
 * `prefers-reduced-motion: reduce` (géré globalement dans tokens.css).
 */
export function Skeleton({ variant = "row", className = "" }: SkeletonProps) {
  const base = "rounded-md bg-skeleton motion-safe:animate-pulse";

  if (variant === "row") {
    return (
      <div className={["flex items-center gap-3", className].join(" ")}>
        <div className={[base, "h-10 w-10 shrink-0 rounded-full"].join(" ")} />
        <div className="flex-1 space-y-2">
          <div className={[base, "h-3 w-3/5"].join(" ")} />
          <div className={[base, "h-3 w-2/5"].join(" ")} />
        </div>
      </div>
    );
  }

  if (variant === "table-row") {
    return <div className={[base, "h-row w-full", className].join(" ")} />;
  }

  if (variant === "kpi") {
    return (
      <div className={["space-y-2", className].join(" ")}>
        <div className={[base, "h-3 w-1/2"].join(" ")} />
        <div className={[base, "h-6 w-1/3"].join(" ")} />
      </div>
    );
  }

  if (variant === "pitch") {
    return <div className={[base, "aspect-[68/105] w-full bg-surface-muted", className].join(" ")} />;
  }

  if (variant === "player-card") {
    // Carte de joueur (docs/ecrans/club-carte-joueur.md A7) : même silhouette
    // (`clip-path`) que `PlayerTradingCard`, puis deux lignes pour « Au club ».
    return (
      <div className={["space-y-3", className].join(" ")}>
        <div
          className="player-trading-card__shape mx-auto h-[320px] w-[280px] bg-skeleton motion-safe:animate-pulse"
        />
        <div className="space-y-2">
          <div className={[base, "h-3 w-3/5"].join(" ")} />
          <div className={[base, "h-3 w-2/5"].join(" ")} />
        </div>
      </div>
    );
  }

  // "card"
  return (
    <div className={["space-y-3 rounded-md border border-border p-3", className].join(" ")}>
      <div className={[base, "h-4 w-2/5"].join(" ")} />
      <div className={[base, "h-3 w-full"].join(" ")} />
      <div className={[base, "h-3 w-4/5"].join(" ")} />
    </div>
  );
}
