import type { StockRow } from "../../api/logistics";
import { HolderSearch } from "./HolderSearch";

/** Au-delà, les puces dépasseraient deux lignes à 360 px : bascule sur la recherche. */
export const HOLDER_PICKER_MAX_CHIPS = 5;

export interface HolderPickerProps {
  label: string;
  /** Répartition du stock de l'article (`stock_by_holder` de l'API). */
  rows: StockRow[];
  /** `null` = « Non localisé » ; `undefined` = aucun choix. */
  value: number | null | undefined;
  onChange: (value: number | null) => void;
  error?: string;
  disabled?: boolean;
}

/**
 * Choix de la source d'une sortie, d'un déplacement ou d'un signalement
 * (spec B4 §0) : puces radio « {nom} · {qté} » construites sur la
 * répartition renvoyée par l'API, jamais recalculée ici.
 */
export function HolderPicker({ label, rows, value, onChange, error, disabled }: HolderPickerProps) {
  if (rows.length > HOLDER_PICKER_MAX_CHIPS) {
    const row = value === undefined ? undefined : rows.find((r) => r.holder_id === value);
    return (
      <div>
        <p className="mb-1 text-sm font-medium text-text">{label}</p>
        <HolderSearch
          value={row ? { id: row.holder_id, name: row.holder_name } : null}
          onChange={(selection) => {
            if (selection) onChange(selection.id);
          }}
          sourceRows={rows}
          ariaLabel={label}
          disabled={disabled}
        />
        {error ? <p className="mt-1 text-xs text-status-danger-fg">{error}</p> : null}
      </div>
    );
  }

  return (
    <div role="radiogroup" aria-label={label}>
      <p className="mb-1 text-sm font-medium text-text">{label}</p>
      <div className="flex flex-wrap gap-1">
        {rows.map((row) => {
          const checked = value !== undefined && row.holder_id === value;
          return (
            // Zone tactile de 44 px autour d'une puce de 36 px.
            <button
              key={row.holder_id ?? "none"}
              type="button"
              role="radio"
              aria-checked={checked}
              disabled={disabled}
              onClick={() => onChange(row.holder_id)}
              className="flex min-h-11 items-center"
            >
              <span
                className={[
                  "flex h-control-sm items-center rounded-full border px-3 text-sm",
                  checked
                    ? "border-primary bg-primary text-on-primary"
                    : "border-border-strong bg-surface text-text hover:bg-surface-muted",
                  row.holder_id === null && !checked ? "text-text-muted" : "",
                ].join(" ")}
              >
                {row.holder_name} · <span className="ml-1 tabular-nums">{row.quantity}</span>
              </span>
            </button>
          );
        })}
      </div>
      {error ? <p className="mt-1 text-xs text-status-danger-fg">{error}</p> : null}
    </div>
  );
}
