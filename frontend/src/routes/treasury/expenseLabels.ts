import type { ExpenseCategory, ExpenseStatus } from "../../api/treasury";
import type { StatusKey } from "../../design-system";
import { formatAmount } from "./money";

/**
 * État d'une dépense (fiche `tresorerie-depenses-assistance.md` §3.1, §3.3) :
 * l'API fournit `status` (« pending », « refused »… CDC 4.5.2) et ce module se
 * contente de choisir la clé de couleur du design system — jamais de libellé
 * ni de règle recalculés ici.
 */
export function expenseStatusKey(status: ExpenseStatus): StatusKey {
  return `expense_${status}` as StatusKey;
}

/**
 * Ligne descriptive d'une catégorie de dépense (§3.1, section « Catégories ») :
 * plafond s'il existe, puis justificatif et réservation.
 */
export function describeExpenseCategory(category: ExpenseCategory, currency: string): string {
  const parts: string[] = [];
  if (category.ceiling) parts.push(`Plafond : ${formatAmount(category.ceiling, currency)}`);
  parts.push(category.receipt_required ? "Justificatif obligatoire" : "Justificatif facultatif");
  if (category.good_standing_only) parts.push("Réservée aux membres en ordre");
  return parts.join(" · ");
}
