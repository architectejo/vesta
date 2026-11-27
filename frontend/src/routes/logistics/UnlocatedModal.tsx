import { useQuery } from "@tanstack/react-query";
import { listArticles, listMovements } from "../../api/logistics";
import { Button, Loader, Modal } from "../../design-system";
import { formatDateFr } from "./format";
import { formatQuantity } from "./materielLabels";

export interface UnlocatedModalProps {
  open: boolean;
  canManage: boolean;
  onClose: () => void;
  /** « Localiser » : ouvre « Déplacer du matériel » avec « De : Non localisé ». */
  onLocate: () => void;
}

/**
 * « Non localisé » (spec B4, écart n° 6) : pas de `GET holders/none/`, la
 * modale est construite à partir des articles dont la répartition contient
 * `holder_id: null` et des 5 derniers mouvements `holder=none`.
 */
export function UnlocatedModal({ open, canManage, onClose, onLocate }: UnlocatedModalProps) {
  const articlesQuery = useQuery({
    queryKey: ["logistics", "articles", "unlocated"],
    queryFn: () => listArticles(),
    enabled: open,
  });
  const movementsQuery = useQuery({
    queryKey: ["logistics", "movements", "unlocated-recent"],
    queryFn: () => listMovements({ holder: "none", limit: 5 }),
    enabled: open,
  });

  const rows = (articlesQuery.data?.results ?? [])
    .map((article) => ({ article, row: article.stock_by_holder.find((r) => r.holder_id === null) }))
    .filter((entry) => entry.row && entry.row.quantity > 0);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Non localisé"
      subtitle="Matériel rattaché à aucun détenteur"
      size="md"
      footer={
        <div className="flex w-full items-center justify-end gap-2">
          <Button variant="secondary" size="md" onClick={onClose}>
            Fermer
          </Button>
          {canManage && rows.length > 0 ? (
            <Button variant="primary" size="md" onClick={onLocate}>
              Localiser
            </Button>
          ) : null}
        </div>
      }
    >
      <div className="space-y-4">
        <section>
          <h3 className="mb-2 text-sm font-semibold text-text">Matériel non localisé</h3>
          {articlesQuery.isLoading ? (
            <Loader loading variant="list" count={2} />
          ) : articlesQuery.isError ? (
            <p role="alert" className="text-sm text-status-danger-fg">
              Impossible de charger ce détail. Réessayez.
            </p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-text-muted">Tout le matériel est rattaché à un détenteur.</p>
          ) : (
            <ul className="divide-y divide-border">
              {rows.map(({ article, row }) => (
                <li key={article.id} className="flex items-center justify-between gap-2 py-2">
                  <span className="min-w-0">
                    <span className="block truncate text-sm text-text">{article.name}</span>
                    <span className="block text-[13px] text-text-muted">{article.category_display}</span>
                  </span>
                  <span className="shrink-0 tabular-nums text-sm text-text">
                    {formatQuantity(row!.quantity, article.unit)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section>
          <h3 className="mb-2 text-sm font-semibold text-text">5 derniers mouvements sans détenteur</h3>
          {movementsQuery.isLoading ? (
            <Loader loading variant="list" count={2} />
          ) : (movementsQuery.data?.results.length ?? 0) === 0 ? (
            <p className="text-sm text-text-muted">Aucun mouvement sans détenteur.</p>
          ) : (
            <ul className="divide-y divide-border">
              {movementsQuery.data!.results.map((movement) => (
                <li key={movement.id} className="flex items-center justify-between gap-2 py-2">
                  <span className="min-w-0">
                    <span className="block truncate text-sm text-text">
                      {movement.movement_type_display} · {movement.article.name}
                    </span>
                    <span className="block text-[13px] text-text-muted">{formatDateFr(movement.movement_date)}</span>
                  </span>
                  <span className="shrink-0 tabular-nums text-sm text-text">
                    {movement.signed_quantity > 0 ? "+" : ""}
                    {movement.signed_quantity}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Modal>
  );
}
