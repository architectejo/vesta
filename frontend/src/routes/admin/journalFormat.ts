/** Mise en forme des horodatages du journal (fuseau du club, UTC en repli). */

function safeZone(timeZone: string | null | undefined): string {
  if (!timeZone) return "UTC";
  try {
    new Intl.DateTimeFormat("fr-FR", { timeZone });
    return timeZone;
  } catch {
    return "UTC";
  }
}

export function formatInZone(iso: string, timeZone: string | null | undefined): string {
  return new Intl.DateTimeFormat("fr-FR", {
    timeZone: safeZone(timeZone),
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(iso));
}

export function formatUtc(iso: string): string {
  return `${formatInZone(iso, "UTC")} UTC`;
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value === "" ? "—" : value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
