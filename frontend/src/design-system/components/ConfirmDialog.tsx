import type { ReactNode } from "react";
import { Modal } from "./Modal";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
  loading?: boolean;
  loadingLabel?: string;
  /** Désactive la confirmation (ex. hors connexion) sans fermer la modale. */
  confirmDisabled?: boolean;
  /** Message d'erreur en français clair affiché dans la modale si l'action échoue. */
  error?: string;
}

/**
 * Confirmation d'une action irréversible ou sensible (docs/lot0/design-system.md
 * §3.1 ; CDC 7.2) : titre en question rappelant l'objet, une phrase de
 * conséquence, jamais « OK » ni « Oui ». Pendant l'action, le bouton est
 * désactivé et affiche un loader (pas de double envoi). `danger` pour une
 * annulation ou une dérogation.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Annuler",
  onConfirm,
  onCancel,
  danger = true,
  loading = false,
  loadingLabel,
  confirmDisabled = false,
  error,
}: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      level={2}
      isSubmitting={loading}
      cancelLabel={cancelLabel}
      confirmLabel={confirmLabel}
      confirmVariant={danger ? "danger" : "primary"}
      confirmLoadingLabel={loadingLabel}
      confirmDisabled={confirmDisabled}
      onConfirm={onConfirm}
    >
      {description ? <div className="text-sm text-text-muted">{description}</div> : null}
      {error ? (
        <p role="alert" className="mt-3 text-sm text-status-danger-fg">
          {error}
        </p>
      ) : null}
    </Modal>
  );
}
