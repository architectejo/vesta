import { useState } from "react";
import { Banner, Button, ConfirmDialog, Modal, useToast } from "../../design-system";

/**
 * Modale « Mot de passe temporaire » (superuser-espace.md §4.5 bis ; CDC
 * 7.1, 10.2 n°21). Le mot de passe n'est jamais conservé après fermeture :
 * il ne vit que dans l'état local de ce composant, jamais dans
 * `sessionStorage` ni dans l'URL.
 */
export function TemporaryPasswordModal({
  name,
  email,
  password,
  onClose,
}: {
  name: string;
  email: string;
  password: string;
  onClose: () => void;
}) {
  const { showToast } = useToast();
  const [copied, setCopied] = useState(false);
  const [confirmCloseOpen, setConfirmCloseOpen] = useState(false);

  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
      showToast("Mot de passe copié.");
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      showToast("Copie impossible. Sélectionnez le mot de passe et copiez-le manuellement.");
    }
  }

  function requestClose(): void {
    if (!copied) {
      setConfirmCloseOpen(true);
      return;
    }
    onClose();
  }

  return (
    <>
      <Modal
        open
        onClose={requestClose}
        title={`Mot de passe temporaire de ${name}`}
        size="sm"
        footer={
          <Button variant="primary" onClick={onClose}>
            J'ai noté le mot de passe
          </Button>
        }
      >
        <div className="space-y-4">
          <Banner variant="warning">
            Ce mot de passe ne sera plus jamais affiché. Copiez-le maintenant et transmettez-le à{" "}
            {name} par un canal sûr.
          </Banner>
          <div className="flex items-center gap-2">
            <span className="flex-1 rounded-sm border border-border-strong bg-surface-muted px-3 py-2 font-mono text-base tracking-widest text-text">
              {password}
            </span>
            <Button variant="secondary" onClick={() => void handleCopy()}>
              {copied ? "Copié" : "Copier"}
            </Button>
          </div>
          <p className="text-sm text-text-muted">
            Valable 48 heures, le joueur devra le changer à sa prochaine connexion.
          </p>
          <p className="text-xs text-text-muted">Identifiant : {email}</p>
        </div>
      </Modal>
      <ConfirmDialog
        open={confirmCloseOpen}
        title="Fermer sans avoir copié le mot de passe ?"
        description="Il ne pourra plus être affiché ; il faudra en générer un nouveau."
        confirmLabel="Fermer"
        cancelLabel="Revenir"
        onConfirm={() => {
          setConfirmCloseOpen(false);
          onClose();
        }}
        onCancel={() => setConfirmCloseOpen(false)}
      />
    </>
  );
}
