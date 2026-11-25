import type { ReactNode } from "react";
import type { StatusFamily } from "../components/statusMap";

export interface KpiTileProps {
  label: string;
  /** Valeur déjà formatée par l'appelant (montants au format du club, servis par l'API). */
  value: ReactNode;
  hint?: string;
  /** Pastille de statut facultative ; `statusLabel` est alors obligatoire (jamais la couleur seule). */
  family?: StatusFamily;
  statusLabel?: string;
  onClick?: () => void;
  className?: string;
}

const DOT: Record<StatusFamily, string> = {
  success: "bg-status-success-dot",
  warning: "bg-status-warning-dot",
  danger: "bg-status-danger-dot",
  suspended: "bg-status-suspended-dot",
  neutral: "bg-status-neutral-dot",
};

/** Tuile « chiffre clé » : valeur 20 px tabulaire, libellé 13 px, indice et statut facultatifs. */
export function KpiTile({ label, value, hint, family, statusLabel, onClick, className = "" }: KpiTileProps) {
  const content = (
    <>
      <span className="block text-xs text-text-muted">{label}</span>
      <span className="block text-xl font-semibold tabular-nums text-text">{value}</span>
      {hint ? <span className="block text-xs text-text-muted">{hint}</span> : null}
      {family && statusLabel ? (
        <span className="mt-1 inline-flex items-center gap-1.5 text-xs font-medium text-text">
          <span aria-hidden="true" className={["h-2 w-2 rounded-full", DOT[family]].join(" ")} />
          {statusLabel}
        </span>
      ) : null}
    </>
  );
  const base = ["block min-w-0 rounded-md border border-border bg-surface p-3 text-left", className].join(" ");
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={[
          base,
          "min-h-[44px] w-full hover:bg-surface-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus",
        ].join(" ")}
      >
        {content}
      </button>
    );
  }
  return <div className={base}>{content}</div>;
}
