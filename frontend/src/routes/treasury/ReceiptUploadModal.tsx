import { useEffect, useState } from "react";
import { Banner, Modal } from "../../design-system";

export interface ReceiptUploadModalProps {
  open: boolean;
  isSubmitting: boolean;
  submitError?: string;
  onClose: () => void;
  onSubmit: (file: File) => void;
  /** Niveau d'empilement (3.2) : `2` quand ouverte par-dessus le détail de la dépense. */
  level?: 1 | 2;
}

/**
 * Modale « Ajouter le justificatif » (fiche `tresorerie-depenses-assistance.md`
 * §3.4 ; CDC 4.5.2). Ouverte depuis le détail d'une dépense libérée ou non
 * justifiée. Rôle exact du dépositaire non nommé par le CDC (§9.5 de la
 * fiche) : le bouton n'est proposé que si l'API l'autorise
 * (`can_upload_expense_receipts`), jamais décidé ici.
 */
export function ReceiptUploadModal({
  open,
  isSubmitting,
  submitError,
  onClose,
  onSubmit,
  level = 2,
}: ReceiptUploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!open) {
      setFile(null);
      setError(undefined);
    }
  }, [open]);

  function submit(): void {
    if (!file) {
      setError("Le justificatif (photo ou PDF) est obligatoire.");
      return;
    }
    setError(undefined);
    onSubmit(file);
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Ajouter le justificatif"
      size="md"
      level={level}
      isDirty={file !== null}
      isSubmitting={isSubmitting}
      confirmLabel="Envoyer le justificatif"
      confirmLoadingLabel="Envoi…"
      onConfirm={submit}
    >
      <div className="space-y-3">
        {submitError ? <Banner variant="danger">{submitError}</Banner> : null}
        <div>
          <label className="mb-1 block text-sm font-medium text-text" htmlFor="expense-receipt-file">
            Justificatif
          </label>
          <input
            id="expense-receipt-file"
            type="file"
            accept=".jpg,.jpeg,.png,.webp,.pdf"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="block w-full text-sm text-text"
          />
          <p className="mt-1 text-xs text-text-muted">Les photos sont compressées avant l'envoi.</p>
          {error ? (
            <p role="alert" className="mt-1 text-xs text-status-danger-fg">
              {error}
            </p>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
