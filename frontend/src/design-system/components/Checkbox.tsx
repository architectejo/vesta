import { useId, type ReactNode } from "react";

export interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  /**
   * Aide affichée sous le libellé (13 px, `--color-text-muted`), liée à la
   * case par `aria-describedby`.
   */
  description?: ReactNode;
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
export function Checkbox({ checked, onChange, label, description, error, disabled, id }: CheckboxProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const descriptionId = description ? `${fieldId}-description` : undefined;
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
          aria-describedby={descriptionId}
          className="relative z-[1] mt-0.5 h-4 w-4 shrink-0 rounded-sm border-border-strong text-primary disabled:opacity-60"
        />
        <span>{label}</span>
      </label>
      {description ? (
        // Hors du libellé : le nom accessible de la case reste le libellé seul,
        // l'aide est lue en description.
        <p id={descriptionId} className="-mt-1.5 pb-1 pl-6 text-[13px] text-text-muted">
          {description}
        </p>
      ) : null}
      {error ? <p className="mt-1 text-xs text-status-danger-fg">{error}</p> : null}
    </div>
  );
}
