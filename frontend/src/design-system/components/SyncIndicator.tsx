import { useState } from "react";
import { Modal } from "./Modal";

export interface SyncIndicatorItem {
  id: string;
  label: string;
  createdAt: string;
}

export interface SyncIndicatorProps {
  isOnline: boolean;
  pendingCount: number;
  isSyncing?: boolean;
  items?: SyncIndicatorItem[];
  onRetry?: () => void;
  className?: string;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

/**
 * Indicateur d'actions hors connexion en attente (CDC 6.6, docs/lot0/
 * design-system.md §3.1 « SyncIndicator ») : pastille dans la barre
 * supérieure, masquée tant que rien n'est en attente. Au clic (s'il y a
 * des actions listées), une modale détaille chacune avec son heure réelle
 * de saisie.
 */
export function SyncIndicator({
  isOnline,
  pendingCount,
  isSyncing = false,
  items = [],
  onRetry,
  className = "",
}: SyncIndicatorProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  if (isOnline && pendingCount === 0) return null;

  const label = !isOnline
    ? pendingCount > 0
      ? `Hors connexion — ${pendingCount} en attente`
      : "Hors connexion"
    : isSyncing
      ? "Envoi en cours…"
      : `${pendingCount} action${pendingCount > 1 ? "s" : ""} en attente d'envoi`;

  const dotClass = !isOnline ? "bg-status-neutral-dot" : "bg-status-warning-dot";
  const canOpenDetails = items.length > 0;

  return (
    <>
      <div
        role="status"
        aria-live="polite"
        className={["flex items-center gap-2 text-xs text-text-muted", className].join(" ")}
      >
        <span aria-hidden="true" className={["h-1.5 w-1.5 shrink-0 rounded-full", dotClass].join(" ")} />
        {canOpenDetails ? (
          <button type="button" className="-my-2 py-2 font-medium text-text hover:underline" onClick={() => setDetailsOpen(true)}>
            {label}
          </button>
        ) : (
          <span>{label}</span>
        )}
        {isOnline && pendingCount > 0 && onRetry ? (
          <button type="button" onClick={onRetry} className="-my-2 py-2 font-medium text-primary-text hover:underline">
            Réessayer
          </button>
        ) : null}
      </div>

      <Modal
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        title="Actions en attente d'envoi"
        size="sm"
        hideFooter
      >
        {items.length === 0 ? (
          <p className="text-sm text-text-muted">Aucune action en attente.</p>
        ) : (
          <ul className="divide-y divide-border">
            {items.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 py-2 text-sm text-text">
                <span>{item.label}</span>
                <span className="shrink-0 text-xs text-text-muted">{formatTime(item.createdAt)}</span>
              </li>
            ))}
          </ul>
        )}
      </Modal>
    </>
  );
}
