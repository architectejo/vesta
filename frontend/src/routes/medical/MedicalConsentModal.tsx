import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { getMyPresidentAccess, grantMyPresidentAccess, revokeMyPresidentAccess } from "../../api/medical";
import { ConfirmDialog, Loader, Modal, StatusBadge, useToast } from "../../design-system";
import { formatDateFrLong } from "./medicalFormat";

export interface MedicalConsentModalProps {
  open: boolean;
  onClose: () => void;
}

const QUERY_KEY = ["medical", "me", "president-access"] as const;

/**
 * « Consentement médical » (accès du Président) — medical.md §4.11.
 * Accessible au seul joueur concerné, depuis « Mon profil ». Pas de
 * mise à jour optimiste : l'état affiché est toujours celui du
 * serveur (§4.11 en fin de section).
 *
 * Écart signalé au compte rendu : le troisième état (« accordée à un
 * Président précédent, puis passation ») ne peut pas être distingué de
 * « jamais accordée » avec la réponse actuelle de `GET
 * /medical/me/president-access/` (`{granted, granted_at}` — `granted_at`
 * n'est jamais remis à zéro et aucune date de passation n'est renvoyée).
 * Ce texte plus spécifique nécessite un champ supplémentaire côté API. En
 * attendant, ce cas affiche le texte générique « Non accordée », jamais un
 * texte inventé.
 */
export function MedicalConsentModal({ open, onClose }: MedicalConsentModalProps) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [confirmRevokeOpen, setConfirmRevokeOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);

  const statusQuery = useQuery({
    queryKey: QUERY_KEY,
    queryFn: getMyPresidentAccess,
    enabled: open,
    gcTime: 0,
    staleTime: 0,
  });

  function handleClose(): void {
    setError(undefined);
    onClose();
  }

  async function handleGrant(): Promise<void> {
    setSubmitting(true);
    setError(undefined);
    try {
      await grantMyPresidentAccess();
      showToast("Autorisation accordée au Président.");
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRevoke(): Promise<void> {
    setSubmitting(true);
    try {
      await revokeMyPresidentAccess();
      showToast("Autorisation révoquée.");
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      setConfirmRevokeOpen(false);
      onClose();
    } finally {
      setSubmitting(false);
    }
  }

  const granted = statusQuery.data?.granted ?? false;

  return (
    <>
      <Modal
        open={open}
        onClose={handleClose}
        title="Autoriser le Président à consulter mon dossier médical complet"
        size="sm"
        isSubmitting={submitting}
        cancelLabel={granted ? "Fermer" : "Annuler"}
        confirmLabel={granted ? "Révoquer" : "Autoriser"}
        confirmVariant={granted ? "danger" : "primary"}
        onConfirm={granted ? () => setConfirmRevokeOpen(true) : () => void handleGrant()}
      >
        {statusQuery.isLoading ? (
          <Loader loading variant="list" count={3} />
        ) : (
          <div className="space-y-3 text-sm">
            <div className="flex items-center gap-2">
              <StatusBadge status={granted ? "medical_consent_granted" : "medical_consent_not_granted"} />
              <span className="text-text">
                {granted && statusQuery.data?.granted_at
                  ? `Autorisation accordée depuis le ${formatDateFrLong(statusQuery.data.granted_at)}.`
                  : "Autorisation non accordée."}
              </span>
            </div>

            <p className="text-text-muted">
              Par défaut, le Président voit seulement votre aptitude (apte, apte avec restriction, inapte) et votre
              date de retour prévue, comme le Coach. Si vous l'autorisez, il pourra aussi consulter votre
              diagnostic, vos blessures et leur suivi. Le Coach, lui, ne voit jamais votre diagnostic.
            </p>

            <div className="rounded-md bg-surface-muted p-3 text-text-muted">
              Cette autorisation est donnée à la fonction de Président, pas à la personne. Si le club change de
              Président, votre autorisation ne le suit pas automatiquement ; vous devrez l'accorder à nouveau au
              nouveau titulaire si vous le souhaitez.
            </div>

            <p className="text-text-muted">
              Votre autorisation, sa révocation et chaque consultation de votre dossier par le Président sont
              enregistrées dans le journal du club. Le contenu médical n'y est jamais copié.
            </p>

            {error ? <p className="text-status-danger-fg">{error}</p> : null}
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={confirmRevokeOpen}
        title="Révoquer l'autorisation ?"
        description="La révocation prend effet immédiatement : le Président ne pourra plus consulter votre dossier médical complet."
        confirmLabel="Révoquer"
        loading={submitting}
        onConfirm={() => void handleRevoke()}
        onCancel={() => setConfirmRevokeOpen(false)}
      />
    </>
  );
}
