import { useId } from "react";
import { IconAdd, IconDecrease } from "../icons";
import { IconButton } from "./IconButton";

export interface NumberFieldProps {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  min?: number;
  max?: number;
  step?: number;
  optional?: boolean;
  help?: string;
  error?: string;
  disabled?: boolean;
  id?: string;
}

function clamp(value: number, min?: number, max?: number): number {
  let result = value;
  if (min !== undefined) result = Math.max(min, result);
  if (max !== undefined) result = Math.min(max, result);
  return result;
}

/** Champ numérique avec boutons − / + (docs/lot0/design-system.md §3.1). */
export function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  optional = false,
  help,
  error,
  disabled = false,
  id,
}: NumberFieldProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const helpId = help ? `${fieldId}-help` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;

  function step_(delta: number): void {
    const base = value ?? min ?? 0;
    onChange(clamp(Number((base + delta).toFixed(2)), min, max));
  }

  return (
    <div>
      <label htmlFor={fieldId} className="mb-1 block text-sm font-medium text-text">
        {label}
        {optional ? <span className="font-normal text-text-muted"> (facultatif)</span> : null}
      </label>
      <div className="flex items-center gap-2">
        <IconButton
          aria-label={`Diminuer ${label}`}
          variant="secondary"
          icon={<IconDecrease aria-hidden="true" className="h-4 w-4" />}
          disabled={disabled || (value != null && min != null && value <= min)}
          onClick={() => step_(-step)}
        />
        <input
          id={fieldId}
          type="number"
          inputMode="numeric"
          value={value ?? ""}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={[helpId, errorId].filter(Boolean).join(" ") || undefined}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === "") {
              onChange(null);
              return;
            }
            const parsed = Number(raw);
            if (!Number.isNaN(parsed)) onChange(clamp(parsed, min, max));
          }}
          className={[
            "h-control-md w-20 rounded-sm border bg-surface px-2 text-center text-base text-text",
            "disabled:opacity-60",
            error ? "border-status-danger-fg" : "border-border-strong",
          ].join(" ")}
        />
        <IconButton
          aria-label={`Augmenter ${label}`}
          variant="secondary"
          icon={<IconAdd aria-hidden="true" className="h-4 w-4" />}
          disabled={disabled || (value != null && max != null && value >= max)}
          onClick={() => step_(step)}
        />
      </div>
      {help && !error ? (
        <p id={helpId} className="mt-1 text-xs text-text-muted">
          {help}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="mt-1 text-xs text-status-danger-fg">
          {error}
        </p>
      ) : null}
    </div>
  );
}
