import { ApiError, triggerBlobDownload } from "../../api/client";
import { downloadQuitus, type TransferOffer } from "../../api/mercato";
import { Button, Modal, useToast } from "../../design-system";

export interface WelcomeModalProps {
  open: boolean;
  offer: TransferOffer | null;
  onContinue: () => void;
}

/**
 * « Bienvenue à {club B} » (fiche `mercato.md` §5.4), affichée une fois au
 * déblocage ou à l'acceptation sans dette. « Continuer » recharge
 * l'application : le club actif change côté API (règle 9, CLAUDE.md), et un
 * rechargement complet est la façon la plus sûre de ne conserver aucune
 * donnée en cache de l'ancien club (simplification documentée au compte
 * rendu : pas de vidage sélectif du cache TanStack Query).
 */
export function WelcomeModal({ open, offer, onContinue }: WelcomeModalProps) {
  const { showToast } = useToast();

  async function handleDownload(): Promise<void> {
    if (!offer) return;
    try {
      const { blob, filename } = await downloadQuitus(offer.id);
      triggerBlobDownload(blob, filename);
    } catch (error) {
      showToast(error instanceof ApiError ? error.detail : "Téléchargement impossible. Réessayez.");
    }
  }

  if (!offer) return null;

  return (
    <Modal
      open={open}
      onClose={onContinue}
      title={`Bienvenue à ${offer.target_club.name}`}
      size="sm"
      blocking
      footer={
        <div className="flex w-full items-center justify-between gap-2">
          <Button variant="secondary" size="md" onClick={() => void handleDownload()}>
            Télécharger le quitus
          </Button>
          <Button variant="primary" size="md" onClick={onContinue}>
            Continuer
          </Button>
        </div>
      }
    >
      <p className="text-sm text-text">
        Votre transfert est effectué : vous avez quitté {offer.origin_club.name}
        {offer.completed_at ? ` le ${new Date(offer.completed_at).toLocaleDateString("fr-FR")}` : ""}. Votre adhésion à{" "}
        {offer.target_club.name} est en attente : des frais d'adhésion sont dus pour la finaliser.
      </p>
    </Modal>
  );
}
