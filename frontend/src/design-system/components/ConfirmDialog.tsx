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
}

/**
 * Confirmation d'une action irréversible (docs/lot0/design-system.md §3.1) :
 * titre en question, une phrase de conséquence, jamais « OK » ni « Oui ».
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
      onConfirm={onConfirm}
    >
      {description ? <p className="text-sm text-text-muted">{description}</p> : null}
    </Modal>
  );
}
