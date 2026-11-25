import type { ArchiveCategory, ArchivedDocument } from "../../../api/assemblies";

export const CATEGORY_LABELS: Record<ArchiveCategory, string> = {
  pv_reunion: "PV de réunion",
  convocation: "Convocation",
  autre: "Autre document",
};

/** Libellés de filtre (club-archives.md §3.2) et valeurs d'URL (`?categorie=pv`). */
export const CATEGORY_FILTERS: Array<{ value: ArchiveCategory | ""; label: string; urlValue: string }> = [
  { value: "", label: "Toutes", urlValue: "" },
  { value: "pv_reunion", label: "PV de réunion", urlValue: "pv" },
  { value: "convocation", label: "Convocations", urlValue: "convocation" },
  { value: "autre", label: "Autres", urlValue: "autre" },
];

export function categoryFromUrl(value: string | null): ArchiveCategory | "" {
  return CATEGORY_FILTERS.find((f) => f.urlValue === value && f.value !== "")?.value ?? "";
}

export function categoryToUrl(category: ArchiveCategory | ""): string {
  return CATEGORY_FILTERS.find((f) => f.value === category)?.urlValue ?? "";
}

export function isImageFileName(name: string): boolean {
  return /\.(jpe?g|png|webp)$/i.test(name);
}

export function formatDocumentDate(iso: string, style: "short" | "long" = "short"): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(
    "fr-FR",
    style === "long"
      ? { weekday: "long", day: "numeric", month: "long", year: "numeric" }
      : { weekday: "short", day: "numeric", month: "short", year: "numeric" },
  ).format(date);
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function formatFileSize(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / (1024 * 1024)).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mo`;
}

export function fileFormatLabel(doc: Pick<ArchivedDocument, "file_name" | "file_size">): string {
  const ext = doc.file_name.includes(".") ? doc.file_name.split(".").pop()!.toUpperCase() : "";
  return [ext, doc.file_size !== null ? formatFileSize(doc.file_size) : ""].filter(Boolean).join(" · ") || "—";
}

/** Date du jour au format AAAA-MM-JJ, dans le fuseau local de l'appareil. */
export function todayIso(): string {
  const d = new Date();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}
