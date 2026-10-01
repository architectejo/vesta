import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getGridMonthDetail, type GridMonthDetail } from "../../api/treasury";
import { Modal, StatusBadge, type PlayerSearchResult } from "../../design-system";
import { GRID_STATE_TO_STATUS_KEY } from "./gridCellVisuals";
import { formatAmount, formatDateFr } from "./money";
import { RecordPaymentModal } from "./RecordPaymentModal";

export interface MonthDetailTarget {
  typeId: number;
  year: number;
  membershipId: number;
  month: number;
}

export interface MonthDetailModalProps {
  target: MonthDetailTarget | null;
  currency: string;
  onClose: () => void;
  /** Après enregistrement d'un paiement depuis cette modale (§4.1 de la fiche). */
  onPaymentRecorded: () => void;
}

function playerToSearchResult(player: GridMonthDetail["player"]): PlayerSearchResult {
  return {
    id: player.membership_id,
    firstName: player.first_name,
    lastName: player.last_name,
    number: player.jersey_number,
    photoUrl: player.photo,
  };
}

/**
 * Modale « Détail du mois » (fiche `tresorerie-grille-cotisations.md` §4.1).
 * Toutes les données (montants, état, répartition des paiements) viennent de
 * `ContributionGridMonthView` ; l'interface ne fait qu'afficher.
 */
export function MonthDetailModal({ target, currency, onClose, onPaymentRecorded }: MonthDetailModalProps) {
  const [showRecordPayment, setShowRecordPayment] = useState(false);
  const open = target !== null;

  const query = useQuery({
    queryKey: [
      "treasury",
      "grid-month-detail",
      target?.typeId,
      target?.year,
      target?.membershipId,
      target?.month,
    ],
    queryFn: () => getGridMonthDetail(target!.typeId, target!.year, target!.membershipId, target!.month),
    enabled: open,
  });

  const detail = query.data;
  const title = detail ? `${detail.period_label} — ${detail.player.name}` : "Détail du mois";

  function handleClose(): void {
    setShowRecordPayment(false);
    onClose();
  }

  return (
    <>
      <Modal
        open={open}
        onClose={handleClose}
        title={title}
        subtitle={detail?.contribution_type.name}
        size="md"
        loading={query.isLoading}
        hideFooter={query.isError}
        cancelLabel="Fermer"
        confirmLabel={detail?.can_record_payment ? "Enregistrer un paiement" : undefined}
        onConfirm={detail?.can_record_payment ? () => setShowRecordPayment(true) : undefined}
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
                  {detail.cell.amount_due !== null ? formatAmount(detail.cell.amount_due, currency) : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-text-muted">Montant affecté</span>
                <span className="tabular-nums text-text">{formatAmount(detail.cell.allocated, currency)}</span>
              </div>
              <div className="flex items-center justify-between gap-2 pt-1">
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
                        <span className="tabular-nums text-text">{formatAmount(item.amount, currency)}</span>
                      </div>
                      <p className="mt-1 text-xs text-text-muted">
                        Part affectée à ce mois : {formatAmount(item.allocated, currency)} · Reçu n°{" "}
                        {item.receipt_number} · {item.method_label}
                      </p>
                      {item.spread_label ? (
                        <p className="mt-1 text-xs text-text-muted">{item.spread_label}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ) : null}
      </Modal>

      {detail ? (
        <RecordPaymentModal
          open={showRecordPayment}
          level={2}
          currency={currency}
          initialPlayer={playerToSearchResult(detail.player)}
          initialContributionTypeId={detail.contribution_type.id}
          onClose={() => setShowRecordPayment(false)}
          onRecorded={() => {
            setShowRecordPayment(false);
            onPaymentRecorded();
          }}
        />
      ) : null}
    </>
  );
}
