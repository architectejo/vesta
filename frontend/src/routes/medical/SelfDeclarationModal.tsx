import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { updateMySelfDeclaration } from "../../api/medical";
import { Checkbox, Modal, TextArea, useToast } from "../../design-system";

export interface SelfDeclarationModalProps {
  open: boolean;
  currentDeclaration: string;
  consentMissing: boolean;
  onClose: () => void;
  onUpdated: () => void;
}

/** « Mettre à jour ma déclaration » (medical.md §4.10), niveau 2. */
export function SelfDeclarationModal({
  open,
  currentDeclaration,
  consentMissing,
  onClose,
  onUpdated,
}: SelfDeclarationModalProps) {
  const { showToast } = useToast();
  const [text, setText] = useState(currentDeclaration);
  const [consentChecked, setConsentChecked] = useState(false);
  const [consentError, setConsentError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setText(currentDeclaration);
      setConsentChecked(false);
      setConsentError(undefined);
      setSubmitError(undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function handleSubmit(): Promise<void> {
    if (consentMissing && !consentChecked) {
      setConsentError("Cochez la case pour enregistrer votre déclaration.");
      return;
    }
    setConsentError(undefined);
    setSubmitting(true);
    setSubmitError(undefined);
    try {
      await updateMySelfDeclaration({ self_declaration: text, consent_given: consentChecked });
      showToast("Déclaration enregistrée.");
      onUpdated();
      onClose();
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Mettre à jour ma déclaration"
      size="md"
      level={2}
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <TextArea
          label="Déclaration sur mon état de santé"
          optional
          value={text}
          onChange={setText}
          rows={4}
        />
        {consentMissing ? (
          <Checkbox
            checked={consentChecked}
            onChange={setConsentChecked}
            label="J'accepte que le Médecin du club traite mes données de santé."
            error={consentError}
          />
        ) : null}
        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
