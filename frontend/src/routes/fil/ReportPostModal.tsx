import { useState } from "react";
import { ApiError } from "../../api/client";
import { reportPost } from "../../api/social";
import { Modal, TextArea, useToast } from "../../design-system";

/** Modale « Signaler la publication » (A5.3, 10.2 n° 23). */
export function ReportPostModal({
  open,
  postId,
  onClose,
  onReported,
}: {
  open: boolean;
  postId: number;
  onClose: () => void;
  onReported: () => void;
}) {
  const { showToast } = useToast();
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(): Promise<void> {
    setSubmitting(true);
    try {
      await reportPost(postId, reason.trim());
      showToast("Merci. La publication a été signalée à l'équipe Vesta.");
      onReported();
      onClose();
    } catch (error) {
      // Message de l'API si elle en fournit un ; message réseau seulement hors connexion (status 0).
      showToast(
        error instanceof ApiError && error.status !== 0 && error.detail
          ? error.detail
          : "Connexion impossible. Vérifiez votre réseau et réessayez.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Signaler cette publication ?"
      size="sm"
      level={2}
      isSubmitting={submitting}
      confirmLabel="Signaler"
      confirmLoadingLabel="Envoi…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-3">
        <p className="text-sm text-text">
          L'équipe Vesta sera prévenue et examinera la publication. Elle reste visible en attendant.
        </p>
        <TextArea
          label="Motif (facultatif)"
          value={reason}
          onChange={(v) => setReason(v.slice(0, 500))}
          rows={3}
          maxLength={500}
          showCount
          help="Ex. : propos insultants, image choquante, information personnelle."
        />
      </div>
    </Modal>
  );
}
