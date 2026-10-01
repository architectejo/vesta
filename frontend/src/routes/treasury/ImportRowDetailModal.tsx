import type { ReactNode } from "react";
import type { ContributionImportRow } from "../../api/treasury";
import { Button, Modal, StatusBadge } from "../../design-system";
import { formatAmount, formatDateFr, formatMonthYear } from "./money";

function rowDisplayName(row: ContributionImportRow): string {
  return row.player ? `${row.player.first_name} ${row.player.last_name}`.trim() : row.identity;
}

export interface ImportRowDetailModalProps {
  row: ContributionImportRow | null;
  currency: string;
  onClose: () => void;
}

/**
 * Modale « Détail de la ligne » (fiche `tresorerie-import-cotisations.md`
 * §6.1) : lecture seule, niveau 2, empilée sur l'aperçu. Tout vient tel quel
 * du rapport renvoyé par l'API (CLAUDE.md §2 « Interface »).
 */
export function ImportRowDetailModal({ row, currency, onClose }: ImportRowDetailModalProps) {
  if (!row) return null;

  const afterStatusKey = row.player_status_after?.is_in_good_standing ? "in_good_standing" : "in_debt";

  return (
    <Modal
      open
      onClose={onClose}
      title={`Ligne ${row.line_number} — ${rowDisplayName(row)}`}
      size="md"
      level={2}
      footer={<Button onClick={onClose}>Fermer</Button>}
    >
      <div className="space-y-4">
        <section>
          <h3 className="mb-2 text-sm font-semibold text-text">Paiements qui seront créés</h3>
          {row.payments.length === 0 ? (
            <p className="text-sm text-text-muted">Aucun paiement à créer pour cette ligne.</p>
          ) : (
            <ImportLineTable
              rows={row.payments}
              currency={currency}
              columns={["Mois", "Date de valeur", "Montant", "Origine"]}
              renderRow={(line, index) => (
                <tr key={index} className="border-t border-border">
                  <td className="px-2 py-1">{formatMonthYear(line.period)}</td>
                  <td className="px-2 py-1">{formatDateFr(line.paid_on)}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{formatAmount(line.amount, currency)}</td>
                  <td className="px-2 py-1">
                    {line.origin === "amount" ? "Montant du fichier" : "« ok » non couvert"}
                  </td>
                </tr>
              )}
            />
          )}
        </section>

        {row.already_imported.length > 0 ? (
          <section>
            <h3 className="mb-2 text-sm font-semibold text-text">Déjà importés (ignorés)</h3>
            <ImportLineTable
              rows={row.already_imported}
              currency={currency}
              columns={["Mois", "Date de valeur", "Montant", "Origine"]}
              renderRow={(line, index) => (
                <tr key={index} className="border-t border-border">
                  <td className="px-2 py-1">{formatMonthYear(line.period)}</td>
                  <td className="px-2 py-1">{formatDateFr(line.paid_on)}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{formatAmount(line.amount, currency)}</td>
                  <td className="px-2 py-1">
                    {line.origin === "amount" ? "Montant du fichier" : "« ok » non couvert"}
                  </td>
                </tr>
              )}
            />
          </section>
        ) : null}

        <section>
          <h3 className="mb-2 text-sm font-semibold text-text">Montants dus qui seront créés</h3>
          {row.dues.length === 0 ? (
            <p className="text-sm text-text-muted">Aucun montant dû à créer.</p>
          ) : (
            <ImportLineTable
              rows={row.dues}
              currency={currency}
              columns={["Mois", "Montant", "Échéance"]}
              renderRow={(line, index) => (
                <tr key={index} className="border-t border-border">
                  <td className="px-2 py-1">{formatMonthYear(line.period)}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{formatAmount(line.amount, currency)}</td>
                  <td className="px-2 py-1">{formatDateFr(line.due_date)}</td>
                </tr>
              )}
            />
          )}
        </section>

        <section className="space-y-1 rounded-md bg-surface-muted p-3">
          <h3 className="text-sm font-semibold text-text">Solde</h3>
          <p className="text-sm text-text">
            Avant l'import : {row.balance_before !== null ? formatAmount(row.balance_before, currency) : "—"}
          </p>
          <div className="flex flex-wrap items-center gap-2 text-sm text-text">
            <span>
              Après l'import : {row.balance_after !== null ? formatAmount(row.balance_after, currency) : "—"}
            </span>
            {row.player_status_after ? <StatusBadge status={afterStatusKey} /> : null}
          </div>
        </section>

        {row.warnings.length > 0 ? (
          <section className="space-y-1 rounded-md bg-status-warning-bg p-3">
            <h3 className="text-sm font-semibold text-status-warning-fg">À vérifier</h3>
            {row.warnings.map((warning, index) => (
              <p key={index} className="text-sm text-status-warning-fg">
                {warning}
              </p>
            ))}
          </section>
        ) : null}
      </div>
    </Modal>
  );
}

interface ImportLineTableProps<T> {
  rows: T[];
  currency: string;
  columns: string[];
  renderRow: (line: T, index: number) => ReactNode;
}

function ImportLineTable<T>({ rows, columns, renderRow }: ImportLineTableProps<T>) {
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full border-collapse text-sm">
        <thead className="bg-surface-muted text-xs text-text-muted">
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col" className="px-2 py-1 text-left font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{rows.map((row, index) => renderRow(row, index))}</tbody>
      </table>
    </div>
  );
}
