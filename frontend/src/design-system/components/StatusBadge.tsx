import { STATUS_MAP, type StatusFamily, type StatusKey } from "./statusMap";

export interface StatusBadgeProps {
  status: StatusKey;
  /** Complément affiché après le libellé (ex. « 20 $ », « 1 match »). */
  detail?: string;
  /**
   * Libellé servi tel quel par l'API (ex. « Non éligible. » pour une carte
   * joueur vue par le Coach) : remplace le libellé de la clé, la couleur
   * restant celle de la clé. Jamais un texte écrit en dur par un écran.
   */
  label?: string;
  className?: string;
}

const DOT_CLASS: Record<StatusFamily, string> = {
  success: "bg-status-success-dot",
  warning: "bg-status-warning-dot",
  danger: "bg-status-danger-dot",
  suspended: "bg-status-suspended-dot",
  neutral: "bg-status-neutral-dot",
};

const PILL_CLASS: Record<StatusFamily, string> = {
  success: "bg-status-success-bg text-status-success-fg",
  warning: "bg-status-warning-bg text-status-warning-fg",
  danger: "bg-status-danger-bg text-status-danger-fg",
  suspended: "bg-status-suspended-bg text-status-suspended-fg",
  neutral: "bg-status-neutral-bg text-status-neutral-fg",
};

/**
 * Pastille de statut (docs/lot0/design-system.md §3.7). La couleur et le
 * libellé sont toujours dérivés de la clé fournie par l'API : aucun écran
 * ne passe une couleur. Jamais la couleur seule — le libellé est toujours
 * affiché.
 */
export function StatusBadge({ status, detail, label, className = "" }: StatusBadgeProps) {
  const mapped = STATUS_MAP[status];
  const entry = label && label.trim() ? { ...mapped, label: label.trim() } : mapped;
  // Un complément identique au libellé (ex. libellé de statut renvoyé tel
  // quel par l'API : « En attente · En attente ») n'apporte rien : omis.
  const extra = detail && detail.trim().toLowerCase() !== entry.label.toLowerCase() ? detail : "";
  return (
    <span
      className={[
        "inline-flex h-[22px] items-center gap-1 rounded-full px-2 text-xs font-medium",
        PILL_CLASS[entry.family],
        className,
      ].join(" ")}
    >
      <span aria-hidden="true" className={["h-1.5 w-1.5 rounded-full", DOT_CLASS[entry.family]].join(" ")} />
      <span>
        {entry.label}
        {extra ? ` · ${extra}` : ""}
      </span>
    </span>
  );
}
