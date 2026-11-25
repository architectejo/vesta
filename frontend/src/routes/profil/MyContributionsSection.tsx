import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getMyGrid, type GridCell, type GridMonth } from "../../api/treasury";
import { EmptyState, IconButton, IconChevronLeft, IconChevronRight, Skeleton } from "../../design-system";
import { cellVisual } from "../treasury/gridCellVisuals";
import { MyMonthDetailModal, type MyMonthTarget } from "./MyMonthDetailModal";

const MIN_YEAR = 2000;
/** Pas de cotisation à consulter au-delà de l'année en cours. */
const currentYear = (): number => new Date().getFullYear();

/**
 * Sous-section « Mes cotisations {année} » de « Mon profil »
 * (comptes-mon-profil.md §3.2 ; CDC 4.4.7) : la ligne du joueur dans la grille
 * de chaque type qui le concerne, en mini-grille 4 × 3. États, montants et
 * libellés viennent de `/treasury/my-grid/<année>/` ; aucun calcul ici.
 */
export function MyContributionsSection() {
  const [year, setYear] = useState(currentYear);
  const [target, setTarget] = useState<MyMonthTarget | null>(null);
  const query = useQuery({ queryKey: ["treasury", "my-grid", year], queryFn: () => getMyGrid(year) });
  const grid = query.data;

  return (
    <div className="mt-4" aria-label={`Mes cotisations ${year}`} role="group">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-text">Mes cotisations {year}</h3>
        <div className="flex items-center gap-1">
          <IconButton
            aria-label="Année précédente"
            disabled={year <= MIN_YEAR}
            onClick={() => setYear((value) => value - 1)}
            icon={<IconChevronLeft aria-hidden="true" className="h-5 w-5" />}
          />
          <span className="min-w-[3rem] text-center text-sm tabular-nums text-text">{year}</span>
          <IconButton
            aria-label="Année suivante"
            disabled={year >= currentYear()}
            onClick={() => setYear((value) => value + 1)}
            icon={<IconChevronRight aria-hidden="true" className="h-5 w-5" />}
          />
        </div>
      </div>

      {query.isLoading ? (
        <div role="status" aria-label="Chargement de vos cotisations" className="mt-2 space-y-2">
          <Skeleton variant="row" />
          <Skeleton variant="row" />
        </div>
      ) : query.isError || !grid ? (
        <EmptyState
          variant="error"
          message="Impossible de charger vos cotisations."
          actionLabel="Réessayer"
          onAction={() => void query.refetch()}
        />
      ) : grid.lines.length === 0 ? (
        <EmptyState message="Vous n'êtes rattaché à aucun type de cotisation." />
      ) : (
        <div className="mt-2 space-y-4">
          {grid.lines.map((line) => (
            <div key={line.contribution_type.id}>
              <p className="mb-1 truncate text-sm text-text">{line.contribution_type.name}</p>
              <div className="grid grid-cols-4 gap-1">
                {line.cells.map((cell, index) => (
                  <MiniCell
                    key={cell.period}
                    cell={cell}
                    month={grid.months[index]}
                    onClick={() => setTarget({ typeId: line.contribution_type.id, year, month: cell.month })}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <MyMonthDetailModal target={target} currency={grid?.currency ?? ""} onClose={() => setTarget(null)} />
    </div>
  );
}

function MiniCell({ cell, month, onClick }: { cell: GridCell; month: GridMonth | undefined; onClick: () => void }) {
  const visual = cellVisual(cell);
  const label = month?.label ?? String(cell.month);
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`${month?.long_label ?? label} : ${cell.state_label}, ${visual.text}`}
      className={`flex min-h-[44px] flex-col items-center justify-center rounded-md border border-border px-1 py-1 ${visual.bgClass} ${visual.textClass}`}
    >
      <span className="text-xs">{label}</span>
      <span className="flex items-center gap-1 text-sm tabular-nums">
        {visual.dot}
        {visual.text}
      </span>
    </button>
  );
}
