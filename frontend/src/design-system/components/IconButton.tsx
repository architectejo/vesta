import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  /** Libellé accessible obligatoire en français (ex. « Fermer »). 3.1 */
  "aria-label": string;
  icon: ReactNode;
  /** `sidebar` : bouton posé sur le fond de la barre latérale (jetons `--color-sidebar-*`, §7.2). */
  variant?: "ghost" | "secondary" | "sidebar";
}

/**
 * Bouton icône seule, 40 × 40 px visibles avec zone tactile de 44 px
 * (docs/lot0/design-system.md §3.1).
 */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { icon, variant = "ghost", className = "", disabled, ...rest },
  ref,
) {
  const variantClass =
    variant === "secondary"
      ? "border border-border-strong bg-surface text-text hover:bg-surface-muted"
      : variant === "sidebar"
        ? "text-sidebar-text-muted hover:bg-sidebar-hover-bg hover:text-sidebar-text"
        : "text-text-muted hover:bg-surface-muted hover:text-text";

  return (
    <button
      ref={ref}
      type="button"
      disabled={disabled}
      className={[
        "relative inline-flex h-10 w-10 items-center justify-center rounded-sm",
        "before:absolute before:-inset-1 before:content-['']",
        "transition-colors motion-safe:duration-150 disabled:opacity-60",
        variantClass,
        className,
      ].join(" ")}
      {...rest}
    >
      {icon}
    </button>
  );
});
