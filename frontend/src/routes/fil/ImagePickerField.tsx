import { useId, useRef, useState } from "react";
import { Button } from "../../design-system";
import { ImageValidationError, prepareImageForUpload, validateImageFile } from "./imagePrep";

export interface ImagePickerFieldProps {
  images: File[];
  onChange: (files: File[]) => void;
  /** 4 pour une publication ou un communiqué (4.16) ; 1 pour le chat (C4). */
  max: number;
  maxLabel: string;
  addLabel?: string;
}

/**
 * Sélecteur d'images avec vignettes, compression et redimensionnement à
 * 1 600 px avant l'envoi (fil-public-communication.md A5.1, C4).
 */
export function ImagePickerField({ images, onChange, max, maxLabel, addLabel = "Ajouter des images" }: ImagePickerFieldProps) {
  const inputId = useId();
  const [error, setError] = useState<string | undefined>(undefined);
  const [preparing, setPreparing] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  async function handleFiles(fileList: FileList | null): Promise<void> {
    if (!fileList || fileList.length === 0) return;
    const incoming = Array.from(fileList);
    if (images.length + incoming.length > max) {
      setError(maxLabel);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    setError(undefined);
    setPreparing(true);
    try {
      const prepared: File[] = [];
      for (const file of incoming) {
        validateImageFile(file);
        prepared.push(await prepareImageForUpload(file));
      }
      onChange([...images, ...prepared]);
    } catch (err) {
      setError(err instanceof ImageValidationError ? err.message : "Cette image n'a pas pu être ajoutée.");
    } finally {
      setPreparing(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple={max > 1}
          className="sr-only"
          onChange={(e) => void handleFiles(e.target.files)}
        />
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={preparing || images.length >= max}
          loading={preparing}
          loadingLabel="Préparation de l'image…"
          onClick={() => inputRef.current?.click()}
        >
          {addLabel}
        </Button>
      </div>
      {error ? <p className="mt-1 text-xs text-status-danger-fg">{error}</p> : null}
      {images.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-2">
          {images.map((file, index) => {
            const url = URL.createObjectURL(file);
            return (
              <li key={`${file.name}-${index}`} className="relative">
                <img
                  src={url}
                  alt=""
                  onLoad={() => URL.revokeObjectURL(url)}
                  className="h-[72px] w-[72px] rounded-md object-cover"
                />
                <button
                  type="button"
                  aria-label={`Retirer l'image ${index + 1}`}
                  onClick={() => onChange(images.filter((_, i) => i !== index))}
                  className="absolute -right-1 -top-1 flex h-6 w-6 items-center justify-center rounded-full bg-text text-surface"
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
