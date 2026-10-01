import { useEffect, useRef, useState } from "react";
import { IconButton } from "../../design-system";

export interface KebabMenuItem {
  label: string;
  onSelect: () => void;
  danger?: boolean;
}

/**
 * Menu « … » minimal (docs/lot0/design-system.md n'a pas de composant dédié) :
 * même comportement (voile de clic extérieur, Échap) que le menu « Types
 * archivés » de la grille des cotisations (`GrilleCotisationsPage.tsx`).
 * Utilisé pour « Gérer les catégories » (§3.1) et « Archiver » (§3.5).
 */
export function KebabMenu({ items, ariaLabel = "Plus d'actions" }: { items: KebabMenuItem[]; ariaLabel?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    function handleClick(event: MouseEvent): void {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    function handleKey(event: KeyboardEvent): void {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  if (items.length === 0) return null;

  return (
    <div className="relative" ref={ref}>
      <IconButton
        aria-label={ariaLabel}
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        icon={
          <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
            <circle cx="5" cy="12" r="1.6" />
            <circle cx="12" cy="12" r="1.6" />
            <circle cx="19" cy="12" r="1.6" />
          </svg>
        }
      />
      {open ? (
        <div className="absolute right-0 top-full z-10 mt-1 w-52 rounded-md border border-border bg-surface py-1 shadow-elevated">
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
              className={[
                "flex w-full items-center px-3 py-2 text-left text-sm hover:bg-surface-muted",
                item.danger ? "text-status-danger-fg" : "text-text",
              ].join(" ")}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
