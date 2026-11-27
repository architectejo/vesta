import type { ReactNode } from "react";

export type BannerVariant = "danger" | "warning" | "info" | "readonly" | "support" | "success";

export interface BannerProps {
  variant: BannerVariant;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
  /**
   * Rôle ARIA. Par défaut `alert` (danger) ou `status` (les autres, annoncés
   * poliment). `note` : bandeau statique dont l'apparition n'est pas annoncée
   * (ex. chat, fiche fil-public-communication.md C7.7).
   */
  role?: "alert" | "status" | "note";
}

const VARIANT_CLASSES: Record<BannerVariant, string> = {
  danger: "bg-status-danger-bg text-status-danger-fg",
  warning: "bg-status-warning-bg text-status-warning-fg",
  info: "bg-surface-muted text-text",
  readonly: "bg-status-warning-bg text-status-warning-fg",
  support: "bg-status-suspended-bg text-status-suspended-fg",
  success: "bg-status-success-bg text-status-success-fg",
};

/**
 * Bandeau pleine largeur (docs/lot0/design-system.md §3.1) : `danger`,
 * `warning`, `info`, `readonly`, `support`.
 */
export function Banner({ variant, children, action, className = "", role }: BannerProps) {
  return (
    <div
      role={role ?? (variant === "danger" ? "alert" : "status")}
      className={[
        "flex flex-wrap items-center justify-between gap-2 rounded-md px-3 py-2 text-sm",
        VARIANT_CLASSES[variant],
        className,
      ].join(" ")}
    >
      <span>{children}</span>
      {action}
    </div>
  );
}
