import { useState } from "react";
import { Button, ConfirmDialog, SyncIndicator } from "../../../design-system";
import type { RefusedMeasure } from "./measureTypes";
import type { MeasureOutbox } from "./useMeasureOutbox";

/**
 * Mesures en attente d'envoi (indicateur 6.6) et mesures refusées par l'API,
 * gardées sur le téléphone avec le message du serveur : le Coach peut les
 * réessayer ou les supprimer, rien n'est contourné.
 */
export function PendingMeasures({ outbox, eventId }: { outbox: MeasureOutbox; eventId: number }) {
  const [toDiscard, setToDiscard] = useState<RefusedMeasure | null>(null);
  const refused = outbox.refused.filter((entry) => entry.eventId === eventId);
  const batches = outbox.pendingBatches.filter((item) => item.payload.eventId === eventId);
  const pendingMeasures = batches.reduce((sum, item) => sum + item.payload.body.items.length, 0);

  if (batches.length === 0 && refused.length === 0 && outbox.isOnline) return null;

  return (
    <div className="mb-2 space-y-2">
      <SyncIndicator
        isOnline={outbox.isOnline}
        pendingCount={pendingMeasures}
        isSyncing={outbox.isSyncing}
        items={batches.map((item) => ({
          id: item.id,
          createdAt: item.createdAt,
          label: `${item.payload.testName} · ${item.payload.body.items.length} mesure${item.payload.body.items.length > 1 ? "s" : ""}`,
        }))}
        onRetry={outbox.retryNow}
      />
      {refused.length > 0 ? (
        <section aria-label="Mesures non envoyées" className="rounded-md border border-status-danger-fg p-2">
          <h4 className="text-sm font-semibold text-text">Mesures non envoyées ({refused.length})</h4>
          <p className="text-xs text-text-muted">Elles restent sur ce téléphone. Vous pouvez les réessayer ou les supprimer.</p>
          <ul className="divide-y divide-border">
            {refused.map((entry) => (
              <li key={entry.id} className="space-y-1 py-2">
                <p className="break-words text-sm text-text">
                  <span className="font-medium">{entry.name}</span> · {entry.testName} · {entry.label}
                </p>
                <p role="alert" className="text-xs text-status-danger-fg">
                  {entry.message}
                </p>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => outbox.retryRefused(entry.id)}>
                    Réessayer
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setToDiscard(entry)}>
                    Supprimer
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <ConfirmDialog
        open={toDiscard !== null}
        title="Supprimer cette mesure ?"
        description={toDiscard ? `La mesure de ${toDiscard.name} (${toDiscard.label}) sera perdue.` : undefined}
        confirmLabel="Supprimer"
        onConfirm={() => {
          if (toDiscard) outbox.discardRefused(toDiscard.id);
          setToDiscard(null);
        }}
        onCancel={() => setToDiscard(null)}
      />
    </div>
  );
}
