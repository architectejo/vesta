import type { ReactNode } from "react";
import type { GridCellState } from "../../api/treasury";
import type { StatusKey } from "../../design-system";
import { formatNumber } from "./money";

/**
 * Rendu d'une cellule de la grille des cotisations (docs/lot0/design-system.md
 * §2.6, CDC 4.4.7) : fond, texte et pastille dérivés uniquement de l'état
 * renvoyé par l'API (`GridCell.state`). Aucune règle métier ici — l'état est
 * déjà décidé par `apps.treasury.services` (CLAUDE.md §2 « Interface »).
 *
 * « Les cellules ne reposent jamais sur la seule couleur : la pastille
 * (forme pleine, demi, vide) et le montant portent l'information pour les
 * daltoniens et en plein soleil. » (design-system.md §2.6)
 */

export const GRID_STATE_TO_STATUS_KEY: Record<GridCellState, StatusKey> = {
  paid: "grid_paid",
  partial: "grid_partial",
  overdue: "grid_overdue",
  upcoming: "grid_upcoming",
  free: "grid_free",
  not_due: "grid_not_due",
};

type DotShape = "full" | "half" | "empty";

const DOT_COLOR_VAR: Record<"success" | "warning" | "danger", string> = {
  success: "var(--color-status-success-dot)",
  warning: "var(--color-status-warning-dot)",
  danger: "var(--color-status-danger-dot)",
};

export function GridStateDot({ shape, color }: { shape: DotShape; color: "success" | "warning" | "danger" }) {
  const colorVar = DOT_COLOR_VAR[color];
  if (shape === "full") {
    return <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: colorVar }} />;
  }
  if (shape === "half") {
    return (
      <span
        aria-hidden="true"
        className="h-1.5 w-1.5 shrink-0 rounded-full border"
        style={{ borderColor: colorVar, background: `linear-gradient(90deg, ${colorVar} 50%, transparent 50%)` }}
      />
    );
  }
  return (
    <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full border bg-transparent" style={{ borderColor: colorVar }} />
  );
}

export interface GridCellLike {
  state: GridCellState;
  allocated: string;
}

export interface CellVisual {
  bgClass: string;
  textClass: string;
  text: string;
  dot: ReactNode | null;
}

/** Montant (ou « — »/« 0 ») affiché dans une cellule, sans devise (2.6). */
export function cellAmountText(cell: GridCellLike): string {
  if (cell.state === "overdue") return "0";
  if (cell.state === "upcoming" || cell.state === "not_due") return "—";
  if (cell.state === "free") {
    return Number(cell.allocated) > 0 ? formatNumber(cell.allocated) : "—";
  }
  // paid / partial : montant affecté
  return formatNumber(cell.allocated);
}

export function cellVisual(cell: GridCellLike): CellVisual {
  const text = cellAmountText(cell);
  switch (cell.state) {
    case "paid":
      return { bgClass: "bg-cell-paid-bg", textClass: "text-status-success-fg", text, dot: <GridStateDot shape="full" color="success" /> };
    case "partial":
      return { bgClass: "bg-cell-partial-bg", textClass: "text-status-warning-fg", text, dot: <GridStateDot shape="half" color="warning" /> };
    case "overdue":
      return { bgClass: "bg-cell-unpaid-bg", textClass: "text-status-danger-fg", text, dot: <GridStateDot shape="empty" color="danger" /> };
    case "free":
      return { bgClass: "bg-surface", textClass: "text-text", text, dot: null };
    case "upcoming":
    case "not_due":
    default:
      return { bgClass: "bg-cell-upcoming-bg", textClass: "text-text-muted", text, dot: null };
  }
}
