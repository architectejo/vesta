import { useState } from "react";
import { withdrawArchivedDocument, type ArchivedDocument } from "../../../api/assemblies";
import { ApiError } from "../../../api/client";
import { Banner, Modal, TextArea, useToast } from "../../../design-system";

const REASON_MAX = 300;

/** Modale « Retirer le document » (club-archives.md §4.3), niveau 2, motif obligatoire. */
export function ArchiveWithdrawModal({
  document,
  onClose,
  onWithdrawn,
}: {
  document: ArchivedDocument;
  onClose: () => void;
  onWithdrawn: () => void;
}) {
  const { showToast } = useToast();
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(): Promise<void> {
    setSubmitError(null);
    if (!reason.trim()) {
      setReasonError("Ce champ est obligatoire.");
      return;
    }
    setReasonError(undefined);
    setSubmitting(true);
    try {
      await withdrawArchivedDocument(document.id, reason.trim());
      showToast("Document retiré des archives.");
      onWithdrawn();
    } catch (err) {
      if (err instanceof ApiError && err.fieldError("reason")) {
        setReasonError(err.fieldError("reason"));
      } else {
        setSubmitError(
          err instanceof ApiError ? err.detail : "Connexion impossible. Vérifiez votre réseau et réessayez.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      level={2}
      size="sm"
      title={`Retirer « ${document.title} » des archives ?`}
      isSubmitting={submitting}
      confirmLabel="Retirer"
      confirmLoadingLabel="Retrait…"
      confirmVariant="danger"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-3">
        {submitError ? <Banner variant="danger">{submitError}</Banner> : null}
        <p className="text-sm text-text">
          Le document ne sera plus affiché par défaut dans la liste. Il n'est pas supprimé : il reste conservé et consultable par le Bureau.
        </p>
        <TextArea
          label="Motif du retrait"
          value={reason}
          onChange={(v) => setReason(v.slice(0, REASON_MAX))}
          rows={3}
          maxLength={REASON_MAX}
          showCount
          help="Exemple : doublon, mauvais fichier, document remplacé."
          error={reasonError}
        />
      </div>
    </Modal>
  );
}
