import { useState } from "react";
import { startSupportSession } from "../../api/licences";
import { ApiError } from "../../api/client";
import { setActiveSupportSession } from "../../auth/supportSession";
import { Banner, Modal, TextArea, useToast } from "../../design-system";

/** Modale « Intervenir sur ce club » (superuser-espace.md §4.4 ; CDC 5.4). */
export function StartSupportSessionModal({
  clubId,
  clubName,
  onClose,
}: {
  clubId: number;
  clubName: string;
  onClose: () => void;
}) {
  const { showToast } = useToast();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleStart(): Promise<void> {
    if (!reason.trim()) {
      setError("Indiquez le motif de l'intervention.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const session = await startSupportSession({ club_id: clubId, reason: reason.trim() });
      setActiveSupportSession({
        id: String(session.id),
        clubId: session.club_id,
        clubName: session.club_name,
        reason: session.reason,
        expiresAt: session.expires_at,
      });
      showToast("Session de support démarrée.");
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : "La session n'a pas pu démarrer. Réessayez.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Intervenir sur ce club"
      size="md"
      isSubmitting={submitting}
      confirmLabel="Démarrer la session"
      confirmLoadingLabel="Démarrage…"
      onConfirm={() => void handleStart()}
    >
      <div className="space-y-4">
        <p className="text-sm text-text">
          Vous allez agir dans l'espace de {clubName} pendant 60 minutes au plus. Le club verra vos
          actions comme « Système Vesta ». Votre identité réelle et ce motif sont enregistrés dans
          le journal.
        </p>
        {error ? <Banner variant="danger">{error}</Banner> : null}
        <TextArea label="Motif de l'intervention" value={reason} onChange={setReason} />
      </div>
    </Modal>
  );
}
