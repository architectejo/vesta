import { useEffect, useState } from "react";
import type { DownloadResult } from "../../api/client";

export interface AuthenticatedImageProps {
  /** Identifiant stable de l'image : seul déclencheur d'un nouveau chargement. */
  cacheKey: string | number;
  /** Récupère l'image en `Blob` par une vue authentifiée (jamais `MEDIA_URL`). */
  download: () => Promise<DownloadResult>;
  alt: string;
  className?: string;
  onClick?: () => void;
}

/**
 * Image dont l'adresse n'est jamais publique (publication « Club », chat,
 * communiqué — fil-public-communication.md point de sécurité critique et
 * point ouvert 13). Récupérée en `Blob` via une vue authentifiée, comme
 * `AttachmentLink` (routes/treasury), puis affichée par une URL d'objet
 * locale, révoquée au démontage.
 */
export function AuthenticatedImage({
  cacheKey,
  download,
  alt,
  className = "",
  onClick,
}: AuthenticatedImageProps) {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let createdUrl: string | null = null;
    setState("loading");
    setObjectUrl(null);
    download()
      .then(({ blob }) => {
        if (cancelled) return;
        createdUrl = URL.createObjectURL(blob);
        setObjectUrl(createdUrl);
        setState("ready");
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
    // `download` est recréée à chaque rendu par l'appelant ; seul `cacheKey`
    // (l'identifiant de l'image) doit déclencher un nouveau chargement.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey]);

  if (state === "error") {
    return (
      <div
        role="img"
        aria-label="Image indisponible"
        className={["flex flex-col items-center justify-center gap-1 bg-surface-muted", className].join(" ")}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 text-text-muted" fill="none" stroke="currentColor" strokeWidth={1.5}>
          <rect x="4" y="5" width="16" height="14" rx="2" />
          <path d="M8 15l3-3 2 2 3-4 3 5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="text-xs text-text-muted">Image indisponible</span>
      </div>
    );
  }

  if (state === "loading" || !objectUrl) {
    return <div aria-hidden="true" className={["bg-skeleton motion-safe:animate-pulse", className].join(" ")} />;
  }

  return (
    <img
      src={objectUrl}
      alt={alt}
      loading="lazy"
      onClick={onClick}
      className={className}
    />
  );
}
