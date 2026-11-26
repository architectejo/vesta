import { useId, type ReactNode } from "react";

export interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  error?: string;
  disabled?: boolean;
  id?: string;
}

/**
 * Case à cocher (docs/lot0/design-system.md §3.1).
 *
 * La case reste à 16 px, mais toute la ligne (case + libellé) est cliquable
 * et mesure au moins 36 px de haut (`min-h-control-sm`, `py-2`) ; une marge de
 * clic invisible de 4 px en haut et en bas (pseudo-élément, comme `Button`)
 * porte la zone tactile à 44 px sans agrandir ni la case ni le texte (§1.3 ;
 * vérification visuelle B7 : la zone ne faisait que 20 px).
 */
export function Checkbox({ checked, onChange, label, error, disabled, id }: CheckboxProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <div>
      <label
        htmlFor={fieldId}
        className={[
          "relative flex min-h-control-sm items-start gap-2 py-2 text-sm text-text",
          "before:absolute before:inset-x-0 before:-inset-y-1 before:content-['']",
          disabled ? "cursor-not-allowed" : "cursor-pointer",
        ].join(" ")}
      >
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
