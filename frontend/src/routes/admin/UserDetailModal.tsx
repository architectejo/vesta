import { useState } from "react";
import { deactivateAccount, superuserResetPassword } from "../../api/auth";
import type { AccountSearchResult } from "../../api/auth";
import { ApiError } from "../../api/client";
import { Banner, Button, ConfirmDialog, IconButton, Modal, TextArea, useToast } from "../../design-system";
import { TemporaryPasswordModal } from "./TemporaryPasswordModal";

/**
 * Modale « Utilisateur » (superuser-espace.md §4.5).
 *
 * Point ouvert signalé au compte rendu : « Réactiver le compte » n'est pas
 * proposé — aucun endpoint de réactivation n'existe côté API
 * (`apps.accounts.services` n'a qu'un `deactivate_account`, pas de
 * fonction symétrique, et aucune route ne l'expose).
 */
export function UserDetailModal({
  account,
  onClose,
}: {
  account: AccountSearchResult;
  onClose: () => void;
}) {
  const { showToast } = useToast();
  const [menuOpen, setMenuOpen] = useState(false);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);

  const [deactivateOpen, setDeactivateOpen] = useState(false);
  const [deactivateReason, setDeactivateReason] = useState("");
  const [deactivating, setDeactivating] = useState(false);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);

  async function handleReset(): Promise<void> {
    setResetting(true);
    setResetError(null);
    try {
      const result = await superuserResetPassword(account.email);
      setTemporaryPassword(result.temporary_password);
      setResetConfirmOpen(false);
    } catch {
      setResetError("La réinitialisation a échoué. Réessayez.");
    } finally {
      setResetting(false);
    }
  }

  async function handleDeactivate(): Promise<void> {
    if (!deactivateReason.trim()) {
      setDeactivateError("Indiquez le motif.");
      return;
    }
    setDeactivating(true);
    setDeactivateError(null);
    try {
      await deactivateAccount({ user_id: account.id, reason: deactivateReason.trim() });
      showToast("Compte désactivé.");
      setDeactivateOpen(false);
      onClose();
    } catch (err) {
      setDeactivateError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setDeactivating(false);
    }
  }

  if (temporaryPassword) {
    return (
      <TemporaryPasswordModal
        name={`${account.first_name} ${account.last_name}`}
        email={account.email}
        password={temporaryPassword}
        onClose={() => {
          setTemporaryPassword(null);
          onClose();
        }}
      />
    );
  }

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title="Utilisateur"
        size="md"
        footer={
          <div className="flex w-full items-center justify-between gap-2">
            <div className="relative">
              <IconButton
                aria-label="Ouvrir le menu"
                onClick={() => setMenuOpen((v) => !v)}
                icon={<span aria-hidden="true">…</span>}
              />
              {menuOpen ? (
                <div className="absolute bottom-full left-0 mb-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated">
                  {account.is_active ? (
                    <button
                      type="button"
                      onClick={() => {
                        setMenuOpen(false);
                        setDeactivateOpen(true);
                      }}
                      className="flex w-full px-3 py-2 text-left text-sm text-status-danger-fg hover:bg-surface-muted"
                    >
                      Désactiver le compte
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={onClose}>
                Fermer
              </Button>
              <Button variant="primary" onClick={() => setResetConfirmOpen(true)}>
                Réinitialiser le mot de passe
              </Button>
            </div>
          </div>
        }
      >
        <div className="space-y-2 text-sm text-text">
          <p className="text-base font-semibold">
            {account.first_name} {account.last_name}
          </p>
          <p className="text-text-muted">{account.email}</p>
          {account.clubs.map((club) => (
            <p key={club.club_id} className="text-text-muted">
              {club.club_name} · {club.roles.join(", ") || "Joueur"}
            </p>
          ))}
          <p>État : {account.is_active ? "Actif" : "Désactivé"}</p>
        </div>
      </Modal>

      <ConfirmDialog
        open={resetConfirmOpen}
        title={`Réinitialiser le mot de passe de ${account.first_name} ${account.last_name} ?`}
        description={
          <>
            {resetError ? <Banner variant="danger">{resetError}</Banner> : null}
            <p>
              Un mot de passe temporaire sera généré. Il sera valable 48 heures et{" "}
              {account.first_name} devra le changer à sa prochaine connexion.
            </p>
          </>
        }
        confirmLabel="Réinitialiser"
        loading={resetting}
        onConfirm={() => void handleReset()}
        onCancel={() => setResetConfirmOpen(false)}
      />

      <Modal
        open={deactivateOpen}
        onClose={() => setDeactivateOpen(false)}
        title="Désactiver le compte"
        size="md"
        level={2}
        isSubmitting={deactivating}
        confirmLabel="Désactiver"
        confirmVariant="danger"
        onConfirm={() => void handleDeactivate()}
      >
        <div className="space-y-3">
          {deactivateError ? <Banner variant="danger">{deactivateError}</Banner> : null}
          <TextArea label="Motif" value={deactivateReason} onChange={setDeactivateReason} />
        </div>
      </Modal>
    </>
  );
}
