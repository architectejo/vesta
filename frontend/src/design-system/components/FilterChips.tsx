/**
 * Puces de filtre sur une ligne qui défile horizontalement (spec B4 §1.1,
 * §4), « Toutes » en premier. Même rendu que les puces de `CountModal`.
 * Remontée de `routes/logistics` dans le design system en B7 : c'est la
 * source commune des puces de filtre, à 36 px de haut (`h-control-sm`).
 */
export interface FilterChipsProps<T extends string> {
  label: string;
  value: T | "";
  onChange: (value: T | "") => void;
  options: Array<{ value: T; label: string }>;
  allLabel?: string;
}

export function FilterChips<T extends string>({
  label,
  value,
  onChange,
  options,
  allLabel = "Toutes",
}: FilterChipsProps<T>) {
  const chips: Array<{ value: T | ""; label: string }> = [{ value: "", label: allLabel }, ...options];
  return (
    <div role="group" aria-label={label} className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
      {chips.map((chip) => {
        const active = chip.value === value;
        return (
          <button
            key={chip.value || "all"}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(chip.value)}
            className={[
              "h-control-sm shrink-0 whitespace-nowrap rounded-full border px-3 text-sm font-medium",
              active ? "border-primary bg-primary text-on-primary" : "border-border-strong bg-surface text-text",
            ].join(" ")}
          >
            {chip.label}
          </button>
        );
      })}
    </div>
  );
}
