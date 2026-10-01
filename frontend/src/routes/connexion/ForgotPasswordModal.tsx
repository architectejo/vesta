import { useState } from "react";
import { requestPasswordReset } from "../../api/auth";
import { ApiError } from "../../api/client";
import { Banner, Button, Modal, TextField } from "../../design-system";

/**
 * Modale « Mot de passe oublié » (comptes-connexion.md §4.1).
 */
export function ForgotPasswordModal({
  initialEmail,
  onClose,
}: {
  initialEmail: string;
  onClose: () => void;
}) {
  const [email, setEmail] = useState(initialEmail);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit(): Promise<void> {
    setError(null);
    if (!email.trim()) {
      setError("Ce champ est obligatoire.");
      return;
    }
    setSubmitting(true);
    try {
      await requestPasswordReset(email.trim());
      setSent(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError("Trop de demandes envoyées. Réessayez dans quelques minutes.");
      } else if (!navigator.onLine) {
        setError("Cette action nécessite une connexion.");
      } else {
        setError(
          err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <Modal
        open
        onClose={onClose}
        title="Mot de passe oublié"
        size="sm"
        footer={<Button onClick={onClose}>Fermer</Button>}
      >
        <div className="space-y-3">
          <Banner variant="info">Demande envoyée.</Banner>
          <p className="text-sm text-text">
            Si un compte existe avec cette adresse, le support Vesta vous transmettra un mot de
            passe temporaire. Il sera valable 48 heures. À votre prochaine connexion, vous devrez
            choisir un nouveau mot de passe.
          </p>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Mot de passe oublié"
      size="sm"
      isSubmitting={submitting}
      isDirty={email !== initialEmail}
      confirmLabel="Envoyer la demande"
      confirmLoadingLabel="Envoi…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <p className="text-sm text-text">
          Indiquez l'email de votre compte. Votre demande sera transmise au support Vesta, qui
          réinitialisera votre mot de passe. Vous recevrez un mot de passe temporaire, valable 48
          heures, que vous devrez changer dès votre prochaine connexion.
        </p>
        {error ? <Banner variant="danger">{error}</Banner> : null}
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={setEmail}
        />
      </div>
    </Modal>
  );
}
