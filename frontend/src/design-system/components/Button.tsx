import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { IconLoading } from "../icons";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Icône facultative à gauche (16 px), remplacée par un indicateur si `loading`. */
  icon?: ReactNode;
  /** État de chargement (3.1) : icône -> indicateur rotatif, bouton désactivé. */
  loading?: boolean;
  /** Libellé affiché pendant `loading` (ex. « Enregistrement… »). */
  loadingLabel?: string;
  children: ReactNode;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "bg-primary text-on-primary hover:brightness-95 disabled:opacity-60",
  secondary:
    "bg-surface text-text border border-border-strong hover:bg-surface-muted disabled:opacity-60",
  ghost: "bg-transparent text-primary-text hover:bg-surface-muted disabled:opacity-60",
  danger: "bg-button-danger-bg text-button-danger-fg hover:brightness-95 disabled:opacity-60",
};

// Zone tactile ≥ 44 px (2.2) obtenue par une marge de clic invisible plutôt
// qu'en agrandissant le bouton visible : `sm` (36 px) et `md` (40 px) sont
// complétés respectivement par 4 px et 2 px de chaque côté.
const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "h-control-sm px-3 text-sm before:-inset-1",
  md: "h-control-md px-4 text-sm before:-inset-[2px]",
};

/**
 * Bouton de base (docs/lot0/design-system.md §3.1). Une seule variante
 * `primary` par zone : c'est à l'appelant de le respecter, pas à ce
 * composant.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    icon,
    loading = false,
    loadingLabel,
    disabled,
    className = "",
    children,
    type = "button",
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={[
        "relative inline-flex items-center justify-center gap-2 rounded-sm font-medium",
        "transition-colors motion-safe:duration-150",
        "before:absolute before:content-['']", // zone tactile invisible (avant taille)
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className,
      ].join(" ")}
      {...rest}
    >
      {loading ? (
        <IconLoading aria-hidden="true" className="h-4 w-4 shrink-0 motion-safe:animate-icon-spin" />
      ) : (
        icon
      )}
      <span>{loading && loadingLabel ? loadingLabel : children}</span>
    </button>
  );
});
