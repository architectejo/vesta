import type {
  ArticleCategory,
  ArticleCondition,
  DecommissionReason,
  DecommissionStatus,
  DiscrepancyReason,
  ManualMovementType,
  MovementType,
  OriginKind,
} from "../../api/logistics";
import type { StatusKey } from "../../design-system";

/** Libellés et clés de statut (fiches `docs/ecrans/logistique.md` §9 et
 * `logistique-intendance-registre.md`). Les libellés affichés viennent de
 * l'API (`*_display`) ; ces listes ne servent qu'aux formulaires et filtres
 * (choix fermés, jamais de `<select>` de joueur ou d'article). */

/** 10 catégories, dans l'ordre de `Article.REGISTER_ORDER` (API). */
export const ARTICLE_CATEGORY_OPTIONS: Array<{ value: ArticleCategory; label: string }> = [
  { value: "jersey", label: "Maillots" },
  { value: "shorts", label: "Culottes" },
  { value: "socks", label: "Bas" },
  { value: "cleats", label: "Bottines" },
  { value: "balls", label: "Ballons" },
  { value: "bibs", label: "Chasubles" },
  { value: "referee", label: "Arbitrage" },
  { value: "accessories", label: "Accessoires" },
  { value: "furniture", label: "Mobilier" },
  { value: "misc", label: "Matériel divers" },
];

export const ARTICLE_CONDITION_OPTIONS: Array<{ value: ArticleCondition; label: string }> = [
  { value: "new", label: "Neuf" },
  { value: "good", label: "Bon état" },
  { value: "worn", label: "Usé" },
  { value: "damaged", label: "Abîmé" },
  { value: "unknown", label: "Non renseigné" },
];

export const IN_MOVEMENT_TYPE_OPTIONS: Array<{ value: ManualMovementType; label: string }> = [
  { value: "in_purchase", label: "Achat" },
  { value: "in_donation", label: "Dotation" },
  { value: "in_return", label: "Retour" },
  { value: "in_opening", label: "Reprise du registre" },
];

export const OUT_MOVEMENT_TYPE_OPTIONS: Array<{ value: ManualMovementType; label: string }> = [
  { value: "out_distribution", label: "Distribution" },
  { value: "out_loan", label: "Prêt pour un match" },
  { value: "out_wear", label: "Usure" },
  { value: "out_loss", label: "Perte" },
];

/** Les 11 types de mouvement de l'API (filtre du registre des mouvements). */
export const ALL_MOVEMENT_TYPE_OPTIONS: Array<{ value: MovementType; label: string }> = [
  ...IN_MOVEMENT_TYPE_OPTIONS,
  { value: "in_transfer", label: "Transfert reçu" },
  ...OUT_MOVEMENT_TYPE_OPTIONS,
  { value: "out_transfer", label: "Transfert" },
  { value: "out_decommission", label: "Déclassement" },
];

export const DECOMMISSION_REASON_OPTIONS: Array<{ value: DecommissionReason; label: string }> = [
  { value: "worn", label: "Usé" },
  { value: "damaged", label: "Abîmé" },
  { value: "unusable", label: "Hors d'usage" },
  { value: "other", label: "Autre" },
];

export const ORIGIN_KIND_OPTIONS: Array<{ value: OriginKind; label: string }> = [
  { value: "donation", label: "Don" },
  { value: "club_funds", label: "Frais de l'équipe" },
  { value: "unknown", label: "Inconnue" },
];

export const DISCREPANCY_REASON_OPTIONS: Array<{ value: DiscrepancyReason; label: string }> = [
  { value: "theft", label: "Vol" },
  { value: "wear", label: "Usure" },
  { value: "oversight", label: "Oubli" },
  { value: "loss", label: "Perte" },
];

/** Types de mouvement affichant le champ « Joueur concerné » (fiche §4.4). */
export const MOVEMENT_TYPES_WITH_MEMBERSHIP: ManualMovementType[] = [
  "out_distribution",
  "out_loan",
  "in_return",
  "out_loss",
];

/** Types de mouvement affichant le champ « Match » (fiche §4.4). */
export const MOVEMENT_TYPES_WITH_MATCH: ManualMovementType[] = ["out_loan", "in_return"];

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

export function decommissionStatusKey(status: DecommissionStatus): StatusKey {
  if (status === "done") return "decommission_done";
  if (status === "cancelled") return "decommission_cancelled";
  return "decommission_pending";
}

/** Normalisation casse et accents pour les filtres locaux (détenteurs). */
export function normalizeText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

/** « 3 pièces » / « 1 pièce » : formulation constante, le chiffre vient de l'API. */
export function piecesLabel(count: number): string {
  return `${count} ${count > 1 ? "pièces" : "pièce"}`;
}

/** « 1 article », « 2 articles » (carte « Où est le matériel », spec §3.2). */
export function articlesLabel(count: number): string {
  return `${count} ${count > 1 ? "articles" : "article"}`;
}
