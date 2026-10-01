export interface SegmentedControlOption<T extends string> {
  value: T;
  label: string;
}

export interface SegmentedControlProps<T extends string> {
  label: string;
  value: T | null;
  onChange: (value: T) => void;
  options: Array<SegmentedControlOption<T>>;
  error?: string;
  help?: string;
  disabled?: boolean;
  /** Grille 2×2 sous 400 px pour garder les libellés entiers (clubs-creation.md §7). */
  wrapOnMobile?: boolean;
}

/**
 * Choix exclusif entre 2 et 4 options (docs/lot0/design-system.md §3.1),
 * préféré au `<select>`.
 */
export function SegmentedControl<T extends string>({
  label,
  value,
  onChange,
  options,
  error,
  help,
  disabled,
  wrapOnMobile = false,
}: SegmentedControlProps<T>) {
  return (
    <div role="group" aria-label={label}>
      <p className="mb-1 block text-sm font-medium text-text">{label}</p>
      <div
        className={[
          wrapOnMobile ? "grid grid-cols-2 gap-1 xs:flex" : "flex flex-wrap gap-1",
        ].join(" ")}
      >
        {options.map((option) => {
          const active = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              disabled={disabled}
              aria-pressed={active}
              onClick={() => onChange(option.value)}
              className={[
                "h-control-md flex-1 rounded-sm border px-3 text-sm font-medium transition-colors",
                active
                  ? "border-primary bg-primary text-on-primary"
                  : "border-border-strong bg-surface text-text hover:bg-surface-muted",
                "disabled:opacity-60",
              ].join(" ")}
            >
              {option.label}
            </button>
          );
        })}
      </div>
      {help && !error ? <p className="mt-1 text-xs text-text-muted">{help}</p> : null}
      {error ? <p className="mt-1 text-xs text-status-danger-fg">{error}</p> : null}
    </div>
  );
}
