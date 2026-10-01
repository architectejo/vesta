import { useState } from "react";
import { forcedPasswordChange } from "../../api/auth";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { Banner, Modal, PasswordField, useToast } from "../../design-system";

/**
 * Modale bloquante « Changez votre mot de passe » (comptes-connexion.md §4.2,
 * club-accueil.md §3 étape 1). L'API ne distingue pas, dans la réponse de
 * connexion, un mot de passe initial d'un mot de passe temporaire (seul
 * `must_change_password` est exposé, voir `UserSummarySerializer`) : le
 * texte générique ci-dessous couvre les deux cas (point ouvert signalé au
 * compte rendu).
 */
export function ForcedPasswordChangeModal({ onSuccess }: { onSuccess: () => void }) {
  const { logout } = useAuth();
  const { showToast } = useToast();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(): Promise<void> {
    setError(null);
    if (newPassword.length < 8) {
      setError("Le mot de passe doit contenir au moins 8 caractères.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Les deux mots de passe ne correspondent pas.");
      return;
    }
    setSubmitting(true);
    try {
      await forcedPasswordChange({ new_password: newPassword, confirm_password: confirmPassword });
      showToast("Mot de passe modifié.");
      onSuccess();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={() => {
        void logout();
      }}
      blocking
      title="Changez votre mot de passe"
      size="md"
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <p className="text-sm text-text">
          Pour protéger votre compte, choisissez un nouveau mot de passe. Tant que ce n'est pas
          fait, vous ne pouvez consulter aucune donnée.
        </p>
        {error ? <Banner variant="danger">{error}</Banner> : null}
        <PasswordField
          label="Nouveau mot de passe"
          autoComplete="new-password"
          value={newPassword}
          onChange={setNewPassword}
          help="8 caractères minimum, différent de votre email."
        />
        <PasswordField
          label="Confirmez le mot de passe"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={setConfirmPassword}
        />
      </div>
    </Modal>
  );
}
