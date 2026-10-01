import { useState } from "react";
import { suspendLicence, terminateLicence } from "../../api/licences";
import type { Licence } from "../../api/licences";
import { ApiError } from "../../api/client";
import { Banner, Modal, TextArea, TextField, useToast } from "../../design-system";

/** Modale « Suspendre la licence » / « Résilier la licence » (superuser-espace.md §4.3). */
export function SuspendTerminateModal({
  licence,
  mode,
  onClose,
  onSaved,
}: {
  licence: Licence;
  mode: "suspend" | "terminate";
  onClose: () => void;
  onSaved: () => void;
}) {
  const { showToast } = useToast();
  const [reason, setReason] = useState("");
  const [confirmName, setConfirmName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const nameMatches = mode === "suspend" || confirmName === licence.club_name;

  async function handleConfirm(): Promise<void> {
    if (!reason.trim()) {
      setError(
        mode === "suspend"
          ? "Le motif de suspension est obligatoire."
          : "Le motif de résiliation est obligatoire.",
      );
      return;
    }
    if (mode === "terminate" && !nameMatches) return;
    setSubmitting(true);
    setError(null);
    try {
      if (mode === "suspend") {
        await suspendLicence(licence.id, reason.trim());
        showToast("Licence suspendue.");
      } else {
        await terminateLicence(licence.id, { reason: reason.trim(), confirm_club_name: confirmName });
        showToast("Licence résiliée.");
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={mode === "suspend" ? "Suspendre la licence" : "Résilier la licence"}
      size="md"
      isSubmitting={submitting}
      confirmLabel={mode === "suspend" ? "Suspendre" : "Résilier"}
      confirmVariant="danger"
      confirmDisabled={mode === "terminate" && !nameMatches}
      onConfirm={() => void handleConfirm()}
    >
      <div className="space-y-4">
        {error ? <Banner variant="danger">{error}</Banner> : null}
        <p className="text-sm text-text">
          {mode === "suspend"
            ? `Les membres de ${licence.club_name} ne pourront plus accéder à Vesta tant que la licence est suspendue. Ses données restent conservées.`
            : `Cette action met fin à la licence de ${licence.club_name}. Ses données restent conservées.`}
        </p>
        <TextArea label="Motif" value={reason} onChange={setReason} />
        {mode === "terminate" ? (
          <TextField
            label="Saisissez le nom du club pour confirmer"
            value={confirmName}
            onChange={setConfirmName}
            error={confirmName && !nameMatches ? "Le nom saisi ne correspond pas au nom du club." : undefined}
          />
        ) : null}
      </div>
    </Modal>
  );
}
