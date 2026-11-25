import type { ReactNode } from "react";
import { EmptyState } from "../components/EmptyState";
import { Loader } from "../components/Loader";
import { IconChevronRight } from "../icons";

export type ChartCardState = "ready" | "loading" | "error" | "empty";

export interface ChartCardProps {
  title: string;
  /** Chiffre clé (20 px), déjà formaté par l'appelant. */
  value?: ReactNode;
  /** Phrase de lecture (14 px). */
  caption?: string;
  /** Période ou « Aujourd'hui ». */
  periodLabel?: string;
  /** Ouvre le détail : toute la carte devient la zone tactile. */
  onOpen?: () => void;
  openLabel?: string;
  state?: ChartCardState;
  emptyMessage?: string;
  errorMessage?: string;
  onRetry?: () => void;
  /**
   * `true` si le contenu porte ses propres éléments cliquables (graphique avec
   * `onSelect`) : ils passent au-dessus de la zone tactile de la carte.
   */
  interactiveContent?: boolean;
  children?: ReactNode;
  className?: string;
}

/**
 * Carte de tableau de bord : titre 16 px/600, chiffre clé, phrase de lecture,
 * graphique, lien « Voir le détail ». États chargement / vide / erreur
 * intégrés. Toute la carte est cliquable (bouton étiré, un seul arrêt clavier).
 */
export function ChartCard({
  title,
  value,
  caption,
  periodLabel,
  onOpen,
  openLabel = "Voir le détail",
  state = "ready",
  emptyMessage,
  errorMessage,
  onRetry,
  interactiveContent = false,
  children,
  className = "",
}: ChartCardProps) {
  const canOpen = Boolean(onOpen) && (state === "ready" || state === "empty");

  let body: ReactNode;
  if (state === "loading") {
    body = <Loader loading variant="list" listSkeleton="chart" count={1} onRetry={onRetry} />;
  } else if (state === "error") {
    body = (
      <div className="relative z-10">
        <EmptyState
          variant="error"
          message={errorMessage ?? "Impossible de charger cette carte."}
          actionLabel="Réessayer"
          onAction={onRetry}
        />
      </div>
    );
  } else if (state === "empty") {
    body = <EmptyState message={emptyMessage ?? "Aucune donnée sur la période."} />;
  } else {
    body = (
      <>
        {value !== undefined ? (
          <p className="text-xl font-semibold tabular-nums text-text">{value}</p>
        ) : null}
        {caption ? <p className="text-sm text-text-muted">{caption}</p> : null}
        <div className={interactiveContent ? "relative z-10" : undefined}>{children}</div>
      </>
    );
  }

  return (
    <article
      aria-busy={state === "loading"}
      className={[
        "relative flex min-w-0 flex-col gap-2 rounded-md border border-border bg-surface p-3 shadow-card",
        canOpen ? "hover:bg-surface-muted" : "",
        className,
      ].join(" ")}
    >
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-text">{title}</h3>
          {periodLabel ? <p className="text-xs text-text-muted">{periodLabel}</p> : null}
        </div>
        {canOpen ? (
          <button
            type="button"
            onClick={onOpen}
            aria-label={`${openLabel} : ${title}`}
            className="inline-flex min-h-[36px] shrink-0 items-center gap-0.5 text-sm font-medium text-primary-text before:absolute before:inset-0 before:rounded-md before:content-[''] focus-visible:before:outline focus-visible:before:outline-2 focus-visible:before:outline-focus"
          >
            <span aria-hidden="true">{openLabel}</span>
            <IconChevronRight aria-hidden="true" className="h-4 w-4" />
          </button>
        ) : null}
      </header>
      {body}
    </article>
  );
}
