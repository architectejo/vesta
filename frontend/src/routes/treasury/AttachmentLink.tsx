import { useState } from "react";
import { ApiError, triggerBlobDownload, type DownloadResult } from "../../api/client";
import { Button } from "../../design-system";

export interface AttachmentLinkProps {
  label: string;
  download: () => Promise<DownloadResult>;
}

/**
 * Ouverture ou téléchargement d'une pièce jointe privée (justificatif de
 * dépense ou d'assistance sociale), toujours via une vue authentifiée
 * (CLAUDE.md règle n° 10 ; fiche §3.3, §4.2 : « aucun justificatif n'est
 * servi depuis un chemin public »). Le fichier est récupéré en `Blob` par le
 * client HTTP (jeton d'accès), puis ouvert dans un nouvel onglet (aperçu) ou
 * téléchargé si le navigateur bloque l'ouverture.
 */
export function AttachmentLink({ label, download }: AttachmentLinkProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick(): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const { blob, filename } = await download();
      const url = URL.createObjectURL(blob);
      const opened = window.open(url, "_blank", "noopener,noreferrer");
      if (!opened) {
        triggerBlobDownload(blob, filename);
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Impossible d'ouvrir cette pièce jointe. Réessayez.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        loading={loading}
        loadingLabel="Ouverture…"
        onClick={() => void handleClick()}
      >
        {label}
      </Button>
      {error ? (
        <p role="alert" className="mt-1 text-xs text-status-danger-fg">
          {error}
        </p>
      ) : null}
    </div>
  );
}
