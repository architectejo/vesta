/**
 * Préparation d'une image avant envoi (fil-public-communication.md A5.1,
 * C4 : « compression et redimensionnement à 1 600 px de côté max. dans le
 * navigateur avant l'envoi », CDC 6.7). Réutilisé par le fil, les
 * communiqués et le chat.
 */

export const MAX_IMAGE_SIDE_PX = 1600;
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
export const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

export class ImageValidationError extends Error {}

export function validateImageFile(file: File): void {
  if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
    throw new ImageValidationError("Format non accepté : JPEG, PNG ou WebP.");
  }
  if (file.size > MAX_IMAGE_BYTES) {
    throw new ImageValidationError("Fichier trop lourd : 10 Mo maximum.");
  }
}

/**
 * Redimensionne l'image à `MAX_IMAGE_SIDE_PX` de côté maximum via un
 * `<canvas>` hors DOM, puis la réencode. Renvoie le fichier d'origine si la
 * préparation échoue (navigateur sans support canvas, image déjà petite) :
 * on ne bloque jamais un envoi pour cette seule raison.
 */
export async function prepareImageForUpload(file: File): Promise<File> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, MAX_IMAGE_SIDE_PX / Math.max(bitmap.width, bitmap.height));
    if (scale >= 1) {
      bitmap.close?.();
      return file;
    }
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();
    const outputType = file.type === "image/png" ? "image/png" : "image/jpeg";
    const blob: Blob | null = await new Promise((resolve) => canvas.toBlob(resolve, outputType, 0.85));
    if (!blob) return file;
    return new File([blob], file.name, { type: outputType });
  } catch {
    return file;
  }
}
