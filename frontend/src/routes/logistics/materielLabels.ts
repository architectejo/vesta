import type { ArticleCategory, ArticleCondition, DiscrepancyReason, MovementType } from "../../api/logistics";
import type { StatusKey } from "../../design-system";

/** Libellés et clés de statut (fiche `docs/ecrans/logistique.md` §9). Les
 * libellés eux-mêmes viennent de l'API (`*_display`) ; ces listes ne servent
 * qu'aux formulaires (choix fermé, jamais de `<select>` de joueur ou d'article
 * — mais un `SegmentedControl` reste correct pour une liste fermée courte). */

export const ARTICLE_CATEGORY_OPTIONS: Array<{ value: ArticleCategory; label: string }> = [
  { value: "jersey", label: "Maillots" },
  { value: "socks", label: "Bas" },
  { value: "cleats", label: "Bottines" },
  { value: "balls", label: "Ballons" },
  { value: "misc", label: "Matériel divers" },
];

export const ARTICLE_CONDITION_OPTIONS: Array<{ value: ArticleCondition; label: string }> = [
  { value: "new", label: "Neuf" },
  { value: "good", label: "Bon état" },
  { value: "worn", label: "Usé" },
  { value: "damaged", label: "Abîmé" },
];

export const IN_MOVEMENT_TYPE_OPTIONS: Array<{ value: MovementType; label: string }> = [
  { value: "in_purchase", label: "Achat" },
  { value: "in_donation", label: "Dotation" },
  { value: "in_return", label: "Retour" },
];

export const OUT_MOVEMENT_TYPE_OPTIONS: Array<{ value: MovementType; label: string }> = [
  { value: "out_distribution", label: "Distribution" },
  { value: "out_loan", label: "Prêt pour un match" },
  { value: "out_wear", label: "Usure" },
  { value: "out_loss", label: "Perte" },
];

export const DISCREPANCY_REASON_OPTIONS: Array<{ value: DiscrepancyReason; label: string }> = [
  { value: "theft", label: "Vol" },
  { value: "wear", label: "Usure" },
  { value: "oversight", label: "Oubli" },
  { value: "loss", label: "Perte" },
];

/** Types de mouvement affichant le champ « Joueur concerné » (fiche §4.4). */
export const MOVEMENT_TYPES_WITH_MEMBERSHIP: MovementType[] = [
  "out_distribution",
  "out_loan",
  "in_return",
  "out_loss",
];

/** Types de mouvement affichant le champ « Match » (fiche §4.4). */
export const MOVEMENT_TYPES_WITH_MATCH: MovementType[] = ["out_loan", "in_return"];

export function equipmentLineStatusKey(status: "out" | "partially_returned" | "returned"): StatusKey {
  if (status === "returned") return "equipment_returned";
  if (status === "partially_returned") return "equipment_partially_returned";
  return "equipment_out";
}

export function inventoryStatusKey(status: "open" | "closed", blocking: boolean): StatusKey {
  if (status === "closed") return "inventory_closed";
  return blocking ? "inventory_overdue" : "inventory_open";
}

export function inventoryLineStatusKey(status: "no_gap" | "justified" | "to_justify"): StatusKey {
  if (status === "no_gap") return "inventory_line_no_gap";
  if (status === "justified") return "inventory_line_justified";
  return "to_justify";
}
