import { useState } from "react";
import { ApiError, triggerBlobDownload } from "../../api/client";
import { downloadPaymentReceipt } from "../../api/treasury";
import { Button, IconButton, IconDownload, useToast } from "../../design-system";

export interface ReceiptDownloadButtonProps {
  paymentId: number;
  /** « icon » : bouton compact d'une ligne de liste ; « text » : bouton de pied de modale. */
  variant?: "icon" | "text";
}

/**
 * Téléchargement du reçu d'un paiement par une vue authentifiée
 * (GET /treasury/payments/<id>/receipt/ ; CLAUDE.md règle n° 10). Le fichier
 * passe par le client HTTP (jeton), jamais par une URL publique.
 */
export function ReceiptDownloadButton({ paymentId, variant = "icon" }: ReceiptDownloadButtonProps) {
  const { showToast } = useToast();
  const [loading, setLoading] = useState(false);

  async function handleClick(): Promise<void> {
    setLoading(true);
    try {
      const { blob, filename } = await downloadPaymentReceipt(paymentId);
      triggerBlobDownload(blob, filename);
    } catch (error) {
      showToast(
        error instanceof ApiError ? error.detail : "Impossible de télécharger le reçu. Réessayez dans un instant.",
      );
    } finally {
      setLoading(false);
    }
  }

  if (variant === "text") {
    return (
      <Button variant="secondary" size="md" loading={loading} loadingLabel="Téléchargement…" onClick={() => void handleClick()}>
        Télécharger le reçu
      </Button>
    );
  }
  return (
    <IconButton
      aria-label="Télécharger le reçu"
      disabled={loading}
      onClick={() => void handleClick()}
      icon={<IconDownload aria-hidden="true" className="h-5 w-5" />}
    />
  );
}
