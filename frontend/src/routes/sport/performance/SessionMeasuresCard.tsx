import { useState, type ReactNode } from "react";
import type { SessionMeasureSummary } from "../../../api/sport";
import { Button, EmptyState } from "../../../design-system";
import { TestResultsModal } from "./TestResultsModal";

export interface SessionMeasuresCardProps {
  sessionId: number;
  measures: SessionMeasureSummary[];
  /** `capabilities.can_measure` servi par l'API (Coach, Assistant, fenêtre ouverte). */
  canMeasure: boolean;
  /** Ouvre l'écran de mesure ; absent en lecture seule (modale « Séance »). */
  onMeasure?: (testId?: number) => void;
  /** Indicateur d'envoi en attente et mesures refusées (hors connexion). */
  extra?: ReactNode;
}

/** Carte « Mesures de la séance » (A4.3) : une ligne par test mesuré, clic = résultats du test. */
export function SessionMeasuresCard({ sessionId, measures, canMeasure, onMeasure, extra }: SessionMeasuresCardProps) {
  const [open, setOpen] = useState<SessionMeasureSummary | null>(null);
  const measureAllowed = canMeasure && onMeasure !== undefined;

  return (
    <section aria-label="Mesures de la séance" className="rounded-md border border-border p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-text">Mesures de la séance</h3>
        {measureAllowed ? (
          <Button variant="primary" size="sm" onClick={() => onMeasure()}>
            Mesurer
          </Button>
        ) : null}
      </div>
      {extra}
      {measures.length === 0 ? (
        <EmptyState message="Aucune mesure pendant cette séance." />
      ) : (
        <ul className="divide-y divide-border">
          {measures.map((measure) => (
            <li key={measure.test_id}>
              <button type="button" onClick={() => setOpen(measure)} className="block min-h-11 w-full py-2 text-left">
                <span className="block break-words text-sm font-medium text-text">{measure.name}</span>
                <span className="block text-xs text-text-muted">
                  {measure.measured_count} joueur{measure.measured_count > 1 ? "s" : ""} mesuré{measure.measured_count > 1 ? "s" : ""}
                  {measure.best?.display ? ` · meilleur ${measure.best.display}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {open ? (
        <TestResultsModal
          open
          onClose={() => setOpen(null)}
          eventId={sessionId}
          testId={open.test_id}
          testName={open.name}
          onMeasureMore={
            measureAllowed
              ? (testId) => {
                  setOpen(null);
                  onMeasure(testId);
                }
              : undefined
          }
        />
      ) : null}
    </section>
  );
}
