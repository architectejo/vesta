import type { ReactNode } from "react";

/** Pied collant des écrans de mesure (le pied standard de la modale est masqué). */
export function StepFooter({ children }: { children: ReactNode }) {
  return (
    <div className="sticky bottom-0 -mx-4 -mb-4 mt-4 flex items-center gap-2 border-t border-border bg-surface p-3">
      {children}
    </div>
  );
}
