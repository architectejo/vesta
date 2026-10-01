export interface TabItem<T extends string> {
  value: T;
  label: string;
}

export interface TabsProps<T extends string> {
  items: Array<TabItem<T>>;
  value: T;
  onChange: (value: T) => void;
  label: string;
}

/** Onglets horizontaux (docs/lot0/design-system.md §3.1), 40 px. */
export function Tabs<T extends string>({ items, value, onChange, label }: TabsProps<T>) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className="flex gap-4 overflow-x-auto border-b border-border"
    >
      {items.map((item) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.value)}
            className={[
              "h-10 shrink-0 whitespace-nowrap border-b-2 px-1 text-sm font-medium",
              active ? "border-primary text-text" : "border-transparent text-text-muted",
            ].join(" ")}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
