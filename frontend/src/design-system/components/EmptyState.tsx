import type { ReactNode } from "react";
import { IconEmpty, IconError } from "../icons";
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
  /**
   * Action affichée mais désactivée (ex. hors connexion) : l'aide qui en
   * explique la raison passe par `description`, visible au toucher.
   */
  actionDisabled?: boolean;
  className?: string;
}

const DEFAULT_MESSAGE: Record<EmptyStateVariant, string> = {
  default: "Rien à afficher pour l'instant.",
  error: "Impossible de charger cette section.",
  "no-results": "Aucun résultat.",
};

function DefaultIcon({ variant }: { variant: EmptyStateVariant }) {
  if (variant === "error") {
    return <IconError aria-hidden="true" className="h-6 w-6 text-text-muted" strokeWidth={1.5} />;
  }
  return <IconEmpty aria-hidden="true" className="h-6 w-6 text-text-muted" strokeWidth={1.5} />;
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
  actionDisabled = false,
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
        <Button size="sm" variant="secondary" onClick={onAction} disabled={actionDisabled}>
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}
