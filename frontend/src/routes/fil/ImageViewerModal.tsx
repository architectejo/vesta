import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { DownloadResult } from "../../api/client";
import { AuthenticatedImage, IconButton, IconChevronLeft, IconChevronRight, IconClose } from "../../design-system";

export interface ViewerImage {
  id: string | number;
  /** Adresse absolue déjà publique, ou `null` si l'image est privée (voir `download`). */
  url: string | null;
  download?: () => Promise<DownloadResult>;
  alt: string;
}

/**
 * Visionneuse plein écran (fil-public-communication.md A5.4). Aucune action
 * d'écriture, aucun téléchargement proposé.
 */
export function ImageViewerModal({
  images,
  startIndex,
  onClose,
}: {
  images: ViewerImage[];
  startIndex: number;
  onClose: () => void;
}) {
  const [index, setIndex] = useState(startIndex);
  const image = images[index];

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") onClose();
      else if (event.key === "ArrowLeft") setIndex((i) => Math.max(0, i - 1));
      else if (event.key === "ArrowRight") setIndex((i) => Math.min(images.length - 1, i + 1));
    }
    window.addEventListener("keydown", handleKeyDown);
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = originalOverflow;
    };
  }, [images.length, onClose]);

  if (!image) return null;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Image ${index + 1} sur ${images.length}`}
      className="fixed inset-0 z-[70] flex flex-col"
      style={{ backgroundColor: "rgb(0 0 0 / 0.9)" }}
    >
      <div className="flex items-center justify-between p-3">
        <span className="text-sm text-white">
          {index + 1} sur {images.length}
        </span>
        <IconButton
          aria-label="Fermer"
          onClick={onClose}
          className="text-white"
          icon={<IconClose aria-hidden="true" className="h-5 w-5" />}
        />
      </div>
      <div className="relative flex flex-1 items-center justify-center overflow-hidden px-2">
        {index > 0 ? (
          <IconButton
            aria-label="Image précédente"
            onClick={() => setIndex((i) => Math.max(0, i - 1))}
            className="absolute left-2 text-white"
            icon={<IconChevronLeft aria-hidden="true" className="h-5 w-5" />}
          />
        ) : null}
        {image.url ? (
          <img src={image.url} alt={image.alt} className="max-h-full max-w-full object-contain" />
        ) : image.download ? (
          <AuthenticatedImage
            cacheKey={image.id}
            download={image.download}
            alt={image.alt}
            className="max-h-full max-w-full object-contain"
          />
        ) : null}
        {index < images.length - 1 ? (
          <IconButton
            aria-label="Image suivante"
            onClick={() => setIndex((i) => Math.min(images.length - 1, i + 1))}
            className="absolute right-2 text-white"
            icon={<IconChevronRight aria-hidden="true" className="h-5 w-5" />}
          />
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
