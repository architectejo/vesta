import type { ReactNode } from "react";
import { Button } from "./Button";

export type EmptyStateVariant = "default" | "error" | "no-results";

export interface EmptyStateProps {
  variant?: EmptyStateVariant;
  /** Message principal. Par défaut, dépend de la variante (voir 3.6, 4.). */
  message?: string;
  /** Précision facultative (13 px, muted). */
  description?: string;
  /** Icône linéaire 24 px ; une icône par défaut est fournie par variante. */
  icon?: ReactNode;
  /**
   * Action facultative (bouton `sm`, secondaire) : ne la fournir que si le
   * rôle de l'utilisateur la permet (décidé par l'API, jamais par ce
   * composant, 3.6).
   */
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

const DEFAULT_MESSAGE: Record<EmptyStateVariant, string> = {
  default: "Rien à afficher pour l'instant.",
  error: "Impossible de charger cette section.",
  "no-results": "Aucun résultat.",
};

function DefaultIcon({ variant }: { variant: EmptyStateVariant }) {
  if (variant === "error") {
    return (
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="h-6 w-6 text-text-muted"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v5" strokeLinecap="round" />
        <circle cx="12" cy="16" r="0.5" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-6 w-6 text-text-muted"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M8 9h8M8 13h5" strokeLinecap="round" />
    </svg>
  );
}

/**
 * État vide explicite pour chaque section (docs/lot0/design-system.md §3.6).
 * Compact, pas d'illustration.
 */
export function EmptyState({
  variant = "default",
  message,
  description,
  icon,
  actionLabel,
  onAction,
  className = "",
}: EmptyStateProps) {
  const resolvedMessage = message ?? DEFAULT_MESSAGE[variant];
  const showAction = Boolean(actionLabel && onAction);

  return (
    <div
      className={[
        "flex flex-col items-center gap-2 px-3 py-6 text-center",
        className,
      ].join(" ")}
    >
      {icon ?? <DefaultIcon variant={variant} />}
      <p className="text-sm text-text">{resolvedMessage}</p>
      {description ? <p className="text-xs text-text-muted">{description}</p> : null}
      {showAction ? (
        <Button size="sm" variant="secondary" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}
