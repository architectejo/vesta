/**
 * Ouverture sécurisée d'un fichier téléchargé dans un nouvel onglet : seuls
 * les types de la liste autorisée sont rouverts (jamais text/html ni SVG,
 * qui exécuteraient du script sous l'origine de l'application).
 */
export const VIEWABLE_MIME_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/webp"] as const;

export const UNOPENABLE_FILE_MESSAGE = "Ce type de fichier ne peut pas être ouvert.";

/** Recrée le Blob avec un type autorisé, ou renvoie `null` si le type ne l'est pas. */
export function toViewableBlob(blob: Blob): Blob | null {
  const type = blob.type.split(";")[0]?.trim().toLowerCase() ?? "";
  if (!(VIEWABLE_MIME_TYPES as readonly string[]).includes(type)) return null;
  return new Blob([blob], { type });
}
