import { useState } from "react";
import type { GridMonth, GridRow } from "../../api/treasury";
import { Avatar, Modal, StatusBadge, type PlayerSearchResult } from "../../design-system";
import { GRID_STATE_TO_STATUS_KEY, cellAmountText } from "./gridCellVisuals";
import { formatAmount } from "./money";
import { RecordPaymentModal } from "./RecordPaymentModal";

export interface FinancialSituationTarget {
  row: GridRow;
  months: GridMonth[];
  contributionTypeId: number;
  contributionTypeName: string;
  year: number;
}

export interface FinancialSituationModalProps {
  target: FinancialSituationTarget | null;
  currency: string;
  canRecordPayments: boolean;
  onClose: () => void;
  onPaymentRecorded: () => void;
}

function rowToSearchResult(row: GridRow): PlayerSearchResult {
  return {
    id: row.membership_id,
    firstName: row.first_name,
    lastName: row.last_name,
    number: row.jersey_number,
    photoUrl: row.photo,
  };
}

/**
 * Modale « Situation financière » (fiche `tresorerie-tableau-de-bord.md`
 * §4.3), ouverte au clic sur un nom depuis la grille des cotisations (fiche
 * `tresorerie-grille-cotisations.md` §3, point 3).
 *
 * **Version réduite, signalée en compte rendu** : seuls le résumé (solde,
 * montant dû échu, déjà chargés avec la grille) et la ligne du type de
 * cotisation actuellement affiché sont montrés. Les onglets « Impayés »,
 * « Paiements » (historique complet) et « Cotisations libres » du §4.3, ainsi
 * que la ligne de chaque *autre* type dans l'onglet « Grille {année} »,
 * demandent des points d'accès qui n'existent pas encore côté API pour un
 * membre autre que soi-même (liste des paiements filtrée par joueur,
 * périodes impayées par joueur) — à construire par `finance-engine` si cette
 * modale doit couvrir le §4.3 en entier.
 */
export function FinancialSituationModal({
  target,
  currency,
  canRecordPayments,
  onClose,
  onPaymentRecorded,
}: FinancialSituationModalProps) {
  const [showRecordPayment, setShowRecordPayment] = useState(false);
  const open = target !== null;
  const row = target?.row;
  const summary = row?.player_status;
  const statusKey = summary ? (summary.is_in_good_standing ? "in_good_standing" : "in_debt") : undefined;

  function handleClose(): void {
    setShowRecordPayment(false);
    onClose();
  }

  return (
    <>
      <Modal
        open={open}
        onClose={handleClose}
        title="Situation financière"
        subtitle={row ? `${row.first_name} ${row.last_name}` : undefined}
        size="lg"
        cancelLabel="Fermer"
        confirmLabel={canRecordPayments ? "Enregistrer un paiement" : undefined}
        onConfirm={canRecordPayments ? () => setShowRecordPayment(true) : undefined}
      >
        {row && target ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <Avatar name={`${row.first_name} ${row.last_name}`} photoUrl={row.photo} size={40} />
              <div className="min-w-0">
                <p className="truncate text-base font-medium text-text">
                  {row.first_name} {row.last_name}
                </p>
                {row.jersey_number != null ? (
                  <p className="text-xs text-text-muted">n° {row.jersey_number}</p>
                ) : null}
              </div>
              {statusKey ? (
                <StatusBadge
                  status={statusKey}
                  detail={statusKey === "in_debt" && summary ? formatAmount(summary.amount_due, currency) : undefined}
                  className="ml-auto"
                />
              ) : null}
            </div>

            {summary ? (
              <div className="grid grid-cols-2 gap-2 rounded-md bg-surface-muted p-3 text-sm">
                <div>
                  <p className="text-text-muted">Solde</p>
                  <p className="tabular-nums text-text">{formatAmount(summary.balance, currency)}</p>
                </div>
                <div>
                  <p className="text-text-muted">Montant dû échu</p>
                  <p className="tabular-nums text-text">{formatAmount(summary.amount_due, currency)}</p>
                </div>
              </div>
            ) : null}

            <div>
              <h3 className="mb-2 text-sm font-medium text-text">
                Grille {target.year} — {target.contributionTypeName}
              </h3>
              <table className="w-full text-sm">
                <thead className="text-xs text-text-muted">
                  <tr>
                    <th scope="col" className="py-1 text-left font-medium">
                      Mois
                    </th>
                    <th scope="col" className="py-1 text-right font-medium">
                      Montant
                    </th>
                    <th scope="col" className="py-1 pl-2 text-left font-medium">
                      État
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {target.months.map((month, index) => {
                    const cell = row.cells[index];
                    if (!cell) return null;
                    return (
                      <tr key={month.period} className="border-t border-border">
                        <td className="py-1 text-text">{month.long_label}</td>
                        <td className="py-1 text-right tabular-nums text-text">{cellAmountText(cell)}</td>
                        <td className="py-1 pl-2">
                          <StatusBadge status={GRID_STATE_TO_STATUS_KEY[cell.state]} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="border-t border-border font-medium">
                    <td className="py-1 text-text">Total</td>
                    <td className="py-1 text-right tabular-nums text-text">{formatAmount(row.total, currency)}</td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        ) : null}
      </Modal>

      {row ? (
        <RecordPaymentModal
          open={showRecordPayment}
          level={2}
          currency={currency}
          initialPlayer={rowToSearchResult(row)}
          initialContributionTypeId={target?.contributionTypeId}
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
