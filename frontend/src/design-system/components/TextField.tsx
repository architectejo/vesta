import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode } from "react";

export interface TextFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value" | "id"> {
  id?: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Affiche « (facultatif) » après le libellé (docs/lot0/design-system.md §3.1). */
  optional?: boolean;
  help?: string;
  error?: string;
  rightSlot?: ReactNode;
  containerClassName?: string;
}

/**
 * Champ de texte de base (docs/lot0/design-system.md §3.1) : libellé
 * au-dessus, aide et erreur en dessous, jamais d'astérisque pour les champs
 * obligatoires.
 */
export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  {
    id,
    label,
    value,
    onChange,
    optional = false,
    help,
    error,
    rightSlot,
    containerClassName = "",
    className = "",
    required,
    ...rest
  },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const helpId = help ? `${inputId}-help` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;

  return (
    <div className={containerClassName}>
      <label htmlFor={inputId} className="mb-1 block text-sm font-medium text-text">
        {label}
        {optional ? <span className="font-normal text-text-muted"> (facultatif)</span> : null}
      </label>
      <div className="relative">
        <input
          ref={ref}
          id={inputId}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={[helpId, errorId].filter(Boolean).join(" ") || undefined}
          className={[
            "h-control-md w-full rounded-sm border bg-surface px-3 text-base text-text",
            "placeholder:text-text-muted disabled:opacity-60",
            error ? "border-status-danger-fg" : "border-border-strong",
            rightSlot ? "pr-11" : "",
            className,
          ].join(" ")}
          {...rest}
        />
        {rightSlot ? (
          <div className="absolute inset-y-0 right-0 flex items-center pr-2">{rightSlot}</div>
        ) : null}
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
});

export interface PasswordFieldProps
  extends Omit<TextFieldProps, "type" | "rightSlot"> {
  autoComplete?: string;
}

/** `TextField` de mot de passe avec bouton texte « Afficher » / « Masquer ». */
export function PasswordField(props: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  return (
    <TextField
      {...props}
      type={visible ? "text" : "password"}
      rightSlot={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="text-xs font-medium text-primary-text hover:underline"
        >
          {visible ? "Masquer" : "Afficher"}
        </button>
      }
    />
  );
}
