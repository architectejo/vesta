import { useState } from "react";
import { handoverPresidency, searchActiveClubPlayers } from "../../api/clubs";
import { ApiError } from "../../api/client";
import { Banner, ConfirmDialog, Modal, PlayerSearch, useToast } from "../../design-system";
import type { PlayerSearchResult } from "../../design-system";

/**
 * Modale « Transmettre la présidence » (club-comite-bureau.md §4.3 ; CDC
 * 2.3), Président uniquement. `PlayerSearch` bornée aux joueurs inscrits
 * (`status: "active"`).
 *
 * Transmission irréversible pour le Président sortant : confirmation
 * explicite (`ConfirmDialog`), comme toute action sensible (CDC 7.2).
 */
export function PresidencyHandoverModal({
  onClose,
  onTransferred,
}: {
  onClose: () => void;
  onTransferred: () => void;
}) {
  const { showToast } = useToast();
  const [successor, setSuccessor] = useState<PlayerSearchResult | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleTransfer(): Promise<void> {
    if (!successor) return;
    setSubmitting(true);
    setError(null);
    try {
      await handoverPresidency({ to_membership_id: Number(successor.id) });
      showToast(`${successor.firstName} ${successor.lastName} est le nouveau Président.`);
      setConfirmOpen(false);
      onTransferred();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
      setConfirmOpen(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title="Transmettre la présidence"
        size="md"
        isSubmitting={submitting}
        confirmLabel="Transmettre"
        confirmLoadingLabel="Transmission…"
        confirmDisabled={!successor}
        onConfirm={() => setConfirmOpen(true)}
      >
        <div className="space-y-4">
          {error ? <Banner variant="danger">{error}</Banner> : null}
          <p className="text-sm text-text">
            Vous désignez votre successeur. Vous resterez joueur du club, sans le rôle de Président.
            Cette action est immédiate.
          </p>
          <PlayerSearch
            value={successor}
            onChange={setSuccessor}
            searchPlayers={searchActiveClubPlayers}
            ariaLabel="Nouveau président"
            placeholder="Nom ou numéro du joueur"
          />
          <p className="text-xs text-text-muted">
            En cas de blocage, le changement peut être fait par le support Vesta, sur demande écrite
            du club après une assemblée générale.
          </p>
        </div>
      </Modal>
      <ConfirmDialog
        open={confirmOpen}
        title={`Transmettre la présidence à ${successor ? `${successor.firstName} ${successor.lastName}` : "ce joueur"} ?`}
        description="Vous perdrez immédiatement les droits de Président."
        confirmLabel="Transmettre"
        loading={submitting}
        onConfirm={() => void handleTransfer()}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
