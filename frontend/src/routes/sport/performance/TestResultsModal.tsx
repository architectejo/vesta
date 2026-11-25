import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getEventPerformanceResults, type PerformanceResultRow } from "../../../api/performance";
import { Avatar, Banner, Button, EmptyState, Loader, Modal } from "../../../design-system";
import { formatLocalDate } from "./performanceFormat";
import { ResultDetailModal } from "./ResultDetailModal";
import { usePerformanceAccess } from "./usePerformanceAccess";

export interface TestResultsModalProps {
  open: boolean;
  onClose: () => void;
  eventId: number;
  testId: number;
  testName: string;
  /** Coach / Assistant avec la fenêtre ouverte : « Ajouter des mesures ». */
  onMeasureMore?: (testId: number) => void;
}

function secondary(row: PerformanceResultRow): string {
  return row.derived.speed_display ?? row.derived.success_rate_display ?? "";
}

/** « {test} — séance du {date} » (C6.4) : classement de la séance, ou la seule ligne du joueur. */
export function TestResultsModal({ open, onClose, eventId, testId, testName, onMeasureMore }: TestResultsModalProps) {
  const access = usePerformanceAccess();
  const [detailId, setDetailId] = useState<number | null>(null);
  const query = useQuery({
    queryKey: ["sport", "performance", "event-results", eventId, testId],
    queryFn: () => getEventPerformanceResults(eventId, testId),
    enabled: open,
  });
  const data = query.data;
  const subtitle = data
    ? data.scope === "all"
      ? `${data.summary.measured_count} joueur${data.summary.measured_count > 1 ? "s" : ""} mesuré${data.summary.measured_count > 1 ? "s" : ""}${
          data.summary.best ? ` · meilleur ${data.summary.best}` : ""
        }${data.summary.average ? ` · moyenne ${data.summary.average}` : ""}`
      : undefined
    : undefined;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={data ? `${data.test.name} — séance du ${formatLocalDate(data.date)}` : testName}
      subtitle={subtitle}
      loading={query.isLoading}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Fermer
          </Button>
          {data?.window_open && onMeasureMore && access.canManage ? (
            <Button variant="primary" onClick={() => onMeasureMore(testId)}>Ajouter des mesures</Button>
          ) : null}
        </>
      }
    >
      {query.isError ? (
        <EmptyState variant="error" message="Impossible de charger les résultats." actionLabel="Réessayer" onAction={() => void query.refetch()} />
      ) : data ? (
        <div className="space-y-3">
          {!data.window_open ? (
            <Banner variant="readonly">La période de saisie des mesures est terminée : lecture seule.</Banner>
          ) : null}

          {data.results.length === 0 && data.dnf.length === 0 ? (
            <EmptyState message="Aucune mesure pour ce test pendant cette séance." />
          ) : (
            <ol className="divide-y divide-border">
              {data.results.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    onClick={() => setDetailId(row.id)}
                    className="flex min-h-14 w-full items-center gap-2 py-2 text-left"
                  >
                    {data.scope === "all" ? (
                      <span className="w-6 shrink-0 text-center text-sm font-semibold tabular-nums text-text">{row.rank}</span>
                    ) : null}
                    <Avatar name={row.player.name} photoUrl={row.player.photo} size={32} />
                    <span className="min-w-0 flex-1">
                      <span className="block break-words text-sm font-medium text-text">{row.player.name}</span>
                      <span className="block text-xs text-text-muted">
                        {row.method_label}
                        {row.attempts_count > 1 ? ` · Essai ${row.attempt_no} sur ${row.attempts_count}` : ""}
                      </span>
                      {row.personal_record ? (
                        <span className="mt-0.5 inline-block rounded-sm border border-border-strong px-1.5 text-xs text-text">
                          Record personnel
                        </span>
                      ) : null}
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="block text-base font-bold tabular-nums text-text">{row.display}</span>
                      {secondary(row) ? <span className="block text-xs text-text-muted">{secondary(row)}</span> : null}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}

          {data.dnf.length > 0 ? (
            <section aria-label="Abandons" className="border-t border-border pt-2">
              <h3 className="text-sm font-semibold text-text">Abandons</h3>
              <ul className="divide-y divide-border">
                {data.dnf.map((row) => (
                  <li key={row.id}>
                    <button
                      type="button"
                      onClick={() => setDetailId(row.id)}
                      className="flex min-h-11 w-full items-center gap-2 py-1 text-left"
                    >
                      <Avatar name={row.player.name} photoUrl={row.player.photo} size={32} />
                      <span className="min-w-0 flex-1 break-words text-sm text-text">{row.player.name}</span>
                      <span className="shrink-0 text-sm text-text-muted">Abandon</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {data.scope === "mine" && data.my_best_overall ? (
            <p className="text-sm text-text">
              Votre meilleur résultat sur ce test : <strong>{data.my_best_overall.display}</strong> le{" "}
              {formatLocalDate(data.my_best_overall.date)}
            </p>
          ) : null}
        </div>
      ) : (
        <Loader loading variant="list" count={4} />
      )}

      <ResultDetailModal resultId={detailId} onClose={() => setDetailId(null)} canManage={access.canManage} />
    </Modal>
  );
}
