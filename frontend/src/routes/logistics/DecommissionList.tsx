import type { Decommission } from "../../api/logistics";
import { StatusBadge } from "../../design-system";
import { formatDateFr } from "./format";
import { UNLOCATED_LABEL } from "./HolderSearch";
import { decommissionStatusKey, formatQuantity } from "./materielLabels";

/** Lignes de déclassement (carte « À déclasser » et sa liste complète, spec B4 §3.1). */
export function DecommissionRows({
  rows,
  onOpen,
}: {
  rows: Decommission[];
  onOpen: (id: number) => void;
}) {
  return (
    <ul className="divide-y divide-border">
      {rows.map((row) => (
        <li key={row.id}>
          <button
            type="button"
            onClick={() => onOpen(row.id)}
            className="flex min-h-11 w-full items-start justify-between gap-2 py-2 text-left"
          >
            <span className="min-w-0">
              <span className="block text-sm text-text">
                {row.article.name} ·{" "}
                <span className="tabular-nums">
                  {formatQuantity(row.quantity, row.article.unit)}
                </span>
              </span>
              <span className="block text-[13px] text-text-muted">
                {row.reason_display}
                {row.reason_note ? ` — ${row.reason_note}` : ""} · chez {row.holder?.name ?? UNLOCATED_LABEL} · signalé
                le {formatDateFr(row.noted_on)}
              </span>
            </span>
            {/* Badge sur une ligne : « À déclasser » se cassait en deux à 360 px. */}
            <StatusBadge status={decommissionStatusKey(row.status)} className="shrink-0 whitespace-nowrap" />
          </button>
        </li>
      ))}
    </ul>
  );
}
