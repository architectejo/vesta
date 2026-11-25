import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../../api/client";
import {
  getMyPerformanceOverview,
  listPerformanceTests,
  type PerformanceTest,
  type PerformanceTestOverview,
} from "../../../api/performance";
import { Button, EmptyState, Loader } from "../../../design-system";
import { formatLocalDate } from "./performanceFormat";
import { EvolutionModal } from "./EvolutionModal";
import { LeaderboardModal } from "./LeaderboardModal";
import { TestFormModal } from "./TestFormModal";

export interface PerformanceTestsCardProps {
  /** Rôles « L » de la partie C3 (Coach, Assistant, Président, VP, DS) : catalogue et classements. */
  staff: boolean;
  /** Coach, Assistant : création, modification, archivage. */
  canManage: boolean;
}

const refusedAccess = (error: unknown) => error instanceof ApiError && error.status === 403;
const retryUnlessDefinitive = (count: number, error: unknown): boolean =>
  !(error instanceof ApiError && [400, 403, 404].includes(error.status)) && count < 2;

function StaffCatalog({ canManage, archived }: { canManage: boolean; archived: boolean }) {
  const [selected, setSelected] = useState<PerformanceTest | null>(null);
  const query = useQuery({
    queryKey: ["sport", "performance", "tests", archived ? "archived" : "active"],
    queryFn: () => listPerformanceTests(archived ? { archived: "only" } : {}),
    retry: retryUnlessDefinitive,
  });
  if (query.isLoading) return <Loader loading variant="list" count={3} />;
  if (query.isError || !query.data) {
    return (
      <EmptyState
        variant="error"
        message="Impossible de charger les tests de performance."
        actionLabel="Réessayer"
        onAction={() => void query.refetch()}
      />
    );
  }
  const tests = query.data.results;
  if (tests.length === 0) {
    return <EmptyState message={archived ? "Aucun test archivé." : "Aucun test de performance pour l'instant."} />;
  }
  return (
    <>
      <ul className="divide-y divide-border">
        {tests.map((test: PerformanceTestOverview) => (
          <li key={test.id}>
            <button type="button" onClick={() => setSelected(test)} className="block min-h-14 w-full py-2 text-left">
              <span className="block break-words text-sm font-medium text-text">{test.name}</span>
              <span className="block text-xs text-text-muted">{test.kind_text}</span>
              <span className="block text-xs text-text-muted">
                {test.last_measured_on
                  ? `Dernière mesure le ${formatLocalDate(test.last_measured_on)} · ${test.last_measured_count} joueur${test.last_measured_count > 1 ? "s" : ""}`
                  : "Aucune mesure pour l'instant"}
              </span>
              {test.season_best ? (
                <span className="block text-xs text-text-muted">
                  Meilleur de la saison : {test.season_best.display} · {test.season_best.player.name}
                </span>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
      {selected ? (
        <LeaderboardModal open onClose={() => setSelected(null)} test={selected} canManage={canManage && !archived} />
      ) : null}
    </>
  );
}

function MyTests() {
  const [selected, setSelected] = useState<PerformanceTest | null>(null);
  const query = useQuery({
    queryKey: ["sport", "performance", "me"],
    queryFn: getMyPerformanceOverview,
    retry: retryUnlessDefinitive,
  });
  if (query.isLoading) return <Loader loading variant="list" count={2} />;
  if (query.error instanceof ApiError && query.error.status === 404) {
    return <EmptyState message="Aucune fiche joueur n'est associée à votre compte." />;
  }
  if (query.isError || !query.data) {
    return (
      <EmptyState variant="error" message="Impossible de charger vos mesures." actionLabel="Réessayer" onAction={() => void query.refetch()} />
    );
  }
  const rows = query.data.tests;
  if (rows.length === 0) return <EmptyState message="Vous n'avez pas encore de mesure." />;
  return (
    <>
      <ul className="divide-y divide-border">
        {rows.map((row) => (
          <li key={row.test.id}>
            <button type="button" onClick={() => setSelected(row.test)} className="block min-h-14 w-full py-2 text-left">
              <span className="block break-words text-sm font-medium text-text">{row.test.name}</span>
              <span className="block text-xs text-text-muted">
                Meilleur {row.best.display} · dernier {row.last.display} le {formatLocalDate(row.last.date)}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {selected ? <EvolutionModal open onClose={() => setSelected(null)} testId={selected.id} testName={selected.name} /> : null}
    </>
  );
}

/**
 * Carte « Tests de performance » de la page « Entraînements » (C5) : le staff
 * voit le catalogue du club, le joueur seulement « Mes tests ». Les résultats
 * ne sont jamais publics.
 */
export function PerformanceTestsCard({ staff, canManage }: PerformanceTestsCardProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const [archived, setArchived] = useState(false);
  // Un refus (403) du catalogue bascule sur « Mes tests » : l'API reste seule juge.
  const probe = useQuery({
    queryKey: ["sport", "performance", "tests", "active"],
    queryFn: () => listPerformanceTests(),
    enabled: staff,
    retry: retryUnlessDefinitive,
  });
  const showMine = !staff || refusedAccess(probe.error);
  const title = showMine ? "Mes tests" : "Tests de performance";

  return (
    <section aria-label={title} className="rounded-md border border-border bg-surface p-3 shadow-card">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-text">{title}</h3>
        {!showMine && canManage ? (
          <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
            Nouveau test
          </Button>
        ) : null}
      </div>
      {showMine ? <MyTests /> : <StaffCatalog canManage={canManage} archived={archived} />}
      {!showMine ? (
        <Button size="sm" variant="ghost" aria-pressed={archived} onClick={() => setArchived((value) => !value)}>
          {archived ? "Tests actifs" : "Tests archivés"}
        </Button>
      ) : null}
      <TestFormModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </section>
  );
}
