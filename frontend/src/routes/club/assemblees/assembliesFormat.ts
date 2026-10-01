import type { Assembly } from "../../../api/assemblies";

/** « vendredi 3 octobre 2026 » à partir d'une date « YYYY-MM-DD ». */
export function formatDateLong(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
}

/** « 03/10/2026 » à partir d'une date « YYYY-MM-DD » (cartes, plus compact). */
export function formatDateShort(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

/** « 18:30 » à partir d'une heure « HH:MM:SS ». */
export function formatTimeShort(time: string): string {
  return time.slice(0, 5);
}

export function assemblyTypeLabel(type: Assembly["assembly_type"]): string {
  return type === "ordinary" ? "Ordinaire" : "Extraordinaire";
}

export type AssemblyCardStatus = "convened" | "cancelled" | "pv_to_sign" | "closed";

/** État affiché sur la carte : dérivé des seules données déjà calculées par l'API (jamais un calcul métier). */
export function assemblyCardStatus(assembly: Assembly): AssemblyCardStatus {
  if (assembly.status === "cancelled") return "cancelled";
  if (assembly.status === "scheduled") return "convened";
  if (assembly.minutes?.is_complete) return "closed";
  return "pv_to_sign";
}
