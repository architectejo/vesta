import { useId, type ReactNode } from "react";

export interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  error?: string;
  disabled?: boolean;
  id?: string;
}

/** Case à cocher (docs/lot0/design-system.md §3.1). */
export function Checkbox({ checked, onChange, label, error, disabled, id }: CheckboxProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <div>
      <label htmlFor={fieldId} className="flex items-start gap-2 text-sm text-text">
        <input
          id={fieldId}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          aria-invalid={Boolean(error) || undefined}
          className="mt-0.5 h-4 w-4 shrink-0 rounded-sm border-border-strong text-primary disabled:opacity-60"
        />
        <span>{label}</span>
      </label>
      {error ? <p className="mt-1 text-xs text-status-danger-fg">{error}</p> : null}
    </div>
  );
}
