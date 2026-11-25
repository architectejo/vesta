import { useQuery } from "@tanstack/react-query";
import { getMyGridMonthDetail } from "../../api/treasury";
import { Modal, StatusBadge } from "../../design-system";
import { GRID_STATE_TO_STATUS_KEY } from "../treasury/gridCellVisuals";
import { formatAmount, formatDateFr } from "../treasury/money";

export interface MyMonthTarget {
  typeId: number;
  year: number;
  month: number;
}

export interface MyMonthDetailModalProps {
  target: MyMonthTarget | null;
  currency: string;
  onClose: () => void;
}

/**
 * « Détail du mois » du profil (lecture seule ; comptes-mon-profil.md §3.2).
 * Données de `/treasury/my-grid/<type>/<année>/months/<mois>/`.
 */
export function MyMonthDetailModal({ target, currency, onClose }: MyMonthDetailModalProps) {
  const open = target !== null;
  const query = useQuery({
    queryKey: ["treasury", "my-grid-month", target?.typeId, target?.year, target?.month],
    queryFn: () => getMyGridMonthDetail(target!.typeId, target!.year, target!.month),
    enabled: open,
  });
  const detail = query.data;
  const money = detail?.currency || currency;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={detail ? detail.period_label : "Détail du mois"}
      subtitle={detail?.contribution_type.name}
      size="md"
      loading={query.isLoading}
      hideFooter={query.isError}
      cancelLabel="Fermer"
    >
      {query.isError ? (
        <p role="alert" className="text-sm text-status-danger-fg">
          Impossible de charger le détail de ce mois. Réessayez.
        </p>
      ) : detail ? (
        <div className="space-y-4">
          <div className="space-y-2 rounded-md bg-surface-muted p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">Montant dû</span>
              <span className="tabular-nums text-text">
                {detail.cell.amount_due !== null ? formatAmount(detail.cell.amount_due, money) : "—"}
              </span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">Montant affecté</span>
              <span className="tabular-nums text-text">{formatAmount(detail.cell.allocated, money)}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-text-muted">État</span>
              <StatusBadge status={GRID_STATE_TO_STATUS_KEY[detail.cell.state]} />
            </div>
          </div>
          <div>
            <h3 className="mb-2 text-sm font-medium text-text">Paiements</h3>
            {detail.payments.length === 0 ? (
              <p className="text-sm text-text-muted">Aucun paiement n'a alimenté ce mois.</p>
            ) : (
              <ul className="space-y-2">
                {detail.payments.map((item) => (
                  <li key={item.payment_id} className="rounded-md border border-border p-2 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-text">{formatDateFr(item.paid_on)}</span>
                      <span className="tabular-nums text-text">{formatAmount(item.amount, money)}</span>
                    </div>
                    <p className="mt-1 text-xs text-text-muted">
                      Part affectée à ce mois : {formatAmount(item.allocated, money)} · {item.method_label}
                    </p>
                    {item.spread_label ? <p className="mt-1 text-xs text-text-muted">{item.spread_label}</p> : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </Modal>
  );
}
