import { useId, type TextareaHTMLAttributes } from "react";

export interface TextAreaProps
  extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "onChange" | "value" | "id"> {
  id?: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  optional?: boolean;
  help?: string;
  error?: string;
  maxLength?: number;
  showCount?: boolean;
  containerClassName?: string;
}

/** Zone de texte (docs/lot0/design-system.md §3.1), 3 lignes minimum. */
export function TextArea({
  id,
  label,
  value,
  onChange,
  optional = false,
  help,
  error,
  maxLength,
  showCount = false,
  containerClassName = "",
  className = "",
  rows = 3,
  ...rest
}: TextAreaProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const helpId = help ? `${fieldId}-help` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;

  return (
    <div className={containerClassName}>
      <label htmlFor={fieldId} className="mb-1 block text-sm font-medium text-text">
        {label}
        {optional ? <span className="font-normal text-text-muted"> (facultatif)</span> : null}
      </label>
      <textarea
        id={fieldId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        maxLength={maxLength}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={[helpId, errorId].filter(Boolean).join(" ") || undefined}
        className={[
          "w-full rounded-sm border bg-surface px-3 py-2 text-base text-text",
          "placeholder:text-text-muted disabled:opacity-60",
          error ? "border-status-danger-fg" : "border-border-strong",
          className,
        ].join(" ")}
        {...rest}
      />
      <div className="mt-1 flex items-center justify-between gap-2">
        <div>
          {help && !error ? (
            <p id={helpId} className="text-xs text-text-muted">
              {help}
            </p>
          ) : null}
          {error ? (
            <p id={errorId} className="text-xs text-status-danger-fg">
              {error}
            </p>
          ) : null}
        </div>
        {showCount && maxLength ? (
          <p className="shrink-0 text-xs text-text-muted">
            {value.length}/{maxLength}
          </p>
        ) : null}
      </div>
    </div>
  );
}
