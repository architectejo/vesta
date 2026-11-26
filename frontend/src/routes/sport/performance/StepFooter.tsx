import type { ReactNode } from "react";

/**
 * Pied collant des écrans de mesure (le pied standard de la modale est masqué).
 * `-bottom-4` compense le rembourrage (16 px) du corps défilant de la modale :
 * avec `bottom-0`, le pied restait 16 px au-dessus du bord pendant le défilement
 * et laissait voir (et toucher) les lignes du chrono dessous — un « Arrêter »
 * pouvait être déclenché par erreur. `z-20` : les avatars et temps des lignes
 * (`relative z-10`) passaient par-dessus le pied (vérification visuelle B3, CDC 3.2).
 */
export function StepFooter({ children }: { children: ReactNode }) {
  return (
    <div data-step-footer="" className="sticky -bottom-4 z-20 -mx-4 -mb-4 mt-4 flex items-center gap-2 border-t border-border bg-surface p-3">
      {children}
    </div>
  );
}
