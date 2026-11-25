import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../../api/client";
import { getMyPerformanceEvolution, getPlayerPerformanceEvolution, type PerformanceEvolution } from "../../../api/performance";
import { Button, EmptyState, KpiTile, LineChart, Loader, Modal } from "../../../design-system";
import { chartValue, formatLocalDate } from "./performanceFormat";
import { shortDateLabel } from "../statsFormat";

export interface EvolutionModalProps {
  open: boolean;
  onClose: () => void;
  testId: number;
  testName: string;
  /** Joueur consulté par le staff ; absent = « Mon évolution » (joueur connecté). */
  membershipId?: number;
  playerName?: string;
  level?: 1 | 2;
}

const PAGE = 5;

function formatAxis(kind: string) {
  return (value: number) => `${value.toFixed(kind === "timed_distance" ? 2 : 0).replace(".", ",")}${kind === "timed_distance" ? " s" : ""}`;
}

function Body({ data }: { data: PerformanceEvolution }) {
  const [visible, setVisible] = useState(PAGE);
  const kind = data.test.kind;
  const progression = data.progression;
  if (data.points.length === 0) return <EmptyState message="Aucune mesure pour ce test." />;
  const legend = progression?.legend || (kind === "timed_distance" ? "Plus bas = plus rapide" : "");
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <KpiTile label="Meilleur" value={data.best?.display ?? "—"} hint={data.best ? formatLocalDate(data.best.date) : undefined} />
        <KpiTile label="Dernier" value={data.last?.display ?? "—"} hint={data.last ? formatLocalDate(data.last.date) : undefined} />
        <KpiTile label="Progression" value={progression ? progression.delta_display : "—"} hint={progression?.text ?? "Au moins 2 séances nécessaires"} />
      </div>
      {data.points.length >= 2 ? (
        <div>
          <LineChart
            title={`Évolution : ${data.test.name}`}
            labels={data.points.map((point) => shortDateLabel(point.date))}
            series={[
              {
                name: data.test.name,
                values: data.points.map((point) =>
                  chartValue(kind, {
                    time_ms: kind === "timed_distance" ? Number(point.sort_value) : null,
                    distance_m: kind === "distance_in_time" ? point.sort_value : null,
                    count: kind === "repetitions" ? Number(point.sort_value) : null,
                    value: kind === "free" ? point.sort_value : null,
                  }),
                ),
              },
            ]}
            formatValue={formatAxis(kind)}
            emptyMessage="Il faut au moins 2 séances pour afficher une évolution."
          />
          {legend ? <p className="text-xs text-text-muted">{legend}</p> : null}
        </div>
      ) : (
        <p className="text-sm text-text-muted">Il faut au moins 2 séances pour afficher une évolution.</p>
      )}
      <section aria-label="Mesures">
        <h3 className="mb-1 text-sm font-semibold text-text">Mesures</h3>
        <ul className="divide-y divide-border">
          {data.results.slice(0, visible).map((row) => (
            <li key={row.id} className="flex min-h-11 items-center justify-between gap-2 py-1 text-sm">
              <span className="min-w-0">
                <span className="block text-text">{formatLocalDate(row.date)}</span>
                <span className="block text-xs text-text-muted">{row.method_label}</span>
              </span>
              <span className="text-right">
                <span className="block font-semibold tabular-nums text-text">{row.display}</span>
                {row.derived.speed_display ? <span className="block text-xs text-text-muted">{row.derived.speed_display}</span> : null}
              </span>
            </li>
          ))}
        </ul>
        {data.results.length > visible ? (
          <Button size="sm" variant="ghost" onClick={() => setVisible((n) => n + PAGE)}>
            Voir plus
          </Button>
        ) : null}
      </section>
    </div>
  );
}

/** « Évolution : {test} — {joueur} » ou « Mon évolution : {test} » (C6.7). */
export function EvolutionModal({ open, onClose, testId, testName, membershipId, playerName, level = 1 }: EvolutionModalProps) {
  const mine = membershipId === undefined;
  const query = useQuery({
    queryKey: ["sport", "performance", "evolution", mine ? "me" : membershipId, testId],
    queryFn: () => (mine ? getMyPerformanceEvolution(testId) : getPlayerPerformanceEvolution(membershipId, testId)),
    enabled: open,
  });
  const title = mine ? `Mon évolution : ${testName}` : `Évolution : ${testName} — ${playerName ?? ""}`.trim();
  const denied = query.error instanceof ApiError && [403, 404].includes(query.error.status);
  return (
    <Modal open={open} onClose={onClose} level={level} title={title} loading={query.isLoading} hideFooter={false} footer={<Button variant="secondary" onClick={onClose}>Fermer</Button>}>
      {query.isError ? (
        <EmptyState
          variant="error"
          message={denied ? "Vous n'avez pas accès à ces mesures." : "Impossible de charger l'évolution."}
          actionLabel={denied ? undefined : "Réessayer"}
          onAction={denied ? undefined : () => void query.refetch()}
        />
      ) : query.data ? (
        <Body data={query.data} />
      ) : (
        <Loader loading variant="list" count={3} />
      )}
    </Modal>
  );
}
