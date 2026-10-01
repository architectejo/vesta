import { useEffect, useState } from "react";

/**
 * Retourne `value`, mis à jour seulement après `delayMs` sans nouvelle
 * frappe. Utilisé par la recherche de `DataTable` (300 ms, 3.3) et de
 * `PlayerSearch` (250 ms, 3.4).
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
