import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError, triggerBlobDownload } from "../../api/client";
import { getClubIdentity } from "../../api/clubs";
import { downloadQuitus, getOffer, respondOffer, type TransferOffer } from "../../api/mercato";
import { Avatar, Button, ConfirmDialog, Modal, StatusBadge, TransferTimeline, useToast } from "../../design-system";
import { buildTransferTimeline, offerStatusKey } from "./mercatoLabels";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

export interface OfferDetailModalProps {
  offerId: number | null;
  /** Le viewer est le joueur visé par l'offre (fiche §4.3) — sinon un
   * dirigeant (§4.4). Déterminé par l'appelant à partir du profil courant. */
  viewerIsTargetPlayer: boolean;
  /** Club actif du viewer, pour déterminer « l'autre club » du menu « … » (§4.4). */
  viewerClubId?: number;
  onClose: () => void;
  onWriteToClub?: (clubId: number, offerId: number) => void;
  onOpenPublicPlayer?: (membershipId: number) => void;
  /** Appelé une fois quand l'offre bascule vers « Transfert effectué » alors
   * que le viewer est le joueur concerné (§5.4, écran « Bienvenue »). */
  onCompletedForPlayer?: (offer: TransferOffer) => void;
}

/** « Offre reçue » (§4.3, joueur) et « Offre de transfert » (§4.4,
 * dirigeants) : un seul composant, le contenu propre à chaque état varie
 * selon `viewerIsTargetPlayer` et le statut renvoyé par l'API (§5.3).
 * L'interface n'évalue jamais la dette ni le moment du déblocage (§5.1) :
 * relecture à l'ouverture et toutes les 30 s tant que l'offre est bloquée. */
export function OfferDetailModal({
  offerId,
  viewerIsTargetPlayer,
  viewerClubId,
  onClose,
  onWriteToClub,
  onOpenPublicPlayer,
  onCompletedForPlayer,
}: OfferDetailModalProps) {
  const open = offerId !== null;
  const { showToast } = useToast();
  const [confirmAccept, setConfirmAccept] = useState(false);
  const [confirmRefuse, setConfirmRefuse] = useState(false);
  const [responding, setResponding] = useState(false);
  const [responseError, setResponseError] = useState<string | undefined>(undefined);
  const [menuOpen, setMenuOpen] = useState(false);

  const offerQuery = useQuery({
    queryKey: ["mercato", "offer", offerId],
    queryFn: () => getOffer(offerId as number),
    enabled: open,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "blocked_debt" || status === "awaiting_quitus" ? 30_000 : false;
    },
  });
  const offer = offerQuery.data;

  const previousStatus = useRef<string | null>(null);
  useEffect(() => {
    if (!offer) return;
    const wasNotCompleted = previousStatus.current !== null && previousStatus.current !== "completed";
    if (viewerIsTargetPlayer && wasNotCompleted && offer.status === "completed") {
      onCompletedForPlayer?.(offer);
    }
    previousStatus.current = offer.status;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offer?.status]);

  // Lien de paiement du club A (le nôtre, tant que le transfert est bloqué :
  // le joueur en est encore membre) — « Contribuer » (§5.2).
  const clubIdentityQuery = useQuery({
    queryKey: ["clubs", "identity"],
    queryFn: getClubIdentity,
    enabled: open && viewerIsTargetPlayer && offer?.status === "blocked_debt",
  });

  async function handleAccept(): Promise<void> {
    if (!offer) return;
    setResponding(true);
    setResponseError(undefined);
    try {
      await respondOffer(offer.id, true);
      setConfirmAccept(false);
      void offerQuery.refetch();
    } catch (error) {
      setResponseError(apiErrorMessage(error));
    } finally {
      setResponding(false);
    }
  }

  async function handleRefuse(): Promise<void> {
    if (!offer) return;
    setResponding(true);
    setResponseError(undefined);
    try {
      await respondOffer(offer.id, false);
      setConfirmRefuse(false);
      showToast("Offre refusée.");
      void offerQuery.refetch();
    } catch (error) {
      setResponseError(apiErrorMessage(error));
    } finally {
      setResponding(false);
    }
  }

  async function handleDownloadQuitus(): Promise<void> {
    if (!offer) return;
    try {
      const { blob, filename } = await downloadQuitus(offer.id);
      triggerBlobDownload(blob, filename);
    } catch (error) {
      showToast(apiErrorMessage(error));
    }
  }

  if (!offer) {
    return (
      <Modal open={open} onClose={onClose} title="Offre" size="md" loading={offerQuery.isLoading} cancelLabel="Fermer">
        {offerQuery.isError ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            Impossible de charger cette offre. Réessayez.
          </p>
        ) : null}
      </Modal>
    );
  }

  const timeline = buildTransferTimeline(offer, {
    responseStepLabel: viewerIsTargetPlayer ? "Votre réponse" : "Réponse du joueur",
    verificationStepLabel: viewerIsTargetPlayer
      ? `Vérification de votre solde auprès de ${offer.origin_club.name}`
      : `Vérification du solde auprès de ${offer.origin_club.name}`,
  });

  const canContribute =
    viewerIsTargetPlayer && offer.status === "blocked_debt" && clubIdentityQuery.data?.payment_link_configured;

  const otherClubForManager =
    !viewerIsTargetPlayer && viewerClubId !== undefined
      ? viewerClubId === offer.origin_club.id
        ? offer.target_club
        : offer.origin_club
      : null;

  function renderFooter() {
    if (!offer) return null;
    if (viewerIsTargetPlayer) {
      if (offer.status === "sent") {
        return (
          <div className="flex w-full items-center justify-end gap-2">
            <Button variant="secondary" size="md" onClick={() => setConfirmRefuse(true)}>
              Refuser
            </Button>
            <Button variant="primary" size="md" onClick={() => setConfirmAccept(true)}>
              Accepter
            </Button>
          </div>
        );
      }
      if (offer.status === "blocked_debt") {
        return (
          <div className="flex w-full items-center justify-end gap-2">
            <Button variant="secondary" size="md" onClick={onClose}>
              Fermer
            </Button>
            {canContribute ? (
              <Button
                variant="primary"
                size="md"
                onClick={() => window.open(clubIdentityQuery.data!.payment_link_url, "_blank", "noopener,noreferrer")}
              >
                Contribuer
              </Button>
            ) : null}
          </div>
        );
      }
      if (offer.status === "completed") {
        return (
          <div className="flex w-full items-center justify-end gap-2">
            <Button variant="secondary" size="md" onClick={onClose}>
              Fermer
            </Button>
            <Button variant="primary" size="md" onClick={() => void handleDownloadQuitus()}>
              Télécharger le quitus
            </Button>
          </div>
        );
      }
    }
    return (
      <div className="flex w-full items-center justify-end">
        <Button variant="secondary" size="md" onClick={onClose}>
          Fermer
        </Button>
      </div>
    );
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={
          viewerIsTargetPlayer
            ? `Offre de ${offer.target_club.name}`
            : `Offre pour ${offer.player.first_name} ${offer.player.last_name}`
        }
        subtitle={viewerIsTargetPlayer ? undefined : `${offer.origin_club.name} → ${offer.target_club.name}`}
        size="md"
        loading={offerQuery.isLoading}
        footer={renderFooter()}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-2">
            <StatusBadge status={offerStatusKey(offer.status)} />
            {!viewerIsTargetPlayer && onWriteToClub && otherClubForManager ? (
              <div className="relative">
                <Button size="sm" variant="ghost" onClick={() => setMenuOpen((v) => !v)}>
                  …
                </Button>
                {menuOpen ? (
                  <div className="absolute right-0 z-10 mt-1 w-56 rounded-md border border-border bg-surface py-1 shadow-elevated">
                    <button
                      type="button"
                      className="block w-full px-3 py-2 text-left text-sm text-text hover:bg-surface-muted"
                      onClick={() => {
                        setMenuOpen(false);
                        onWriteToClub(otherClubForManager.id, offer.id);
                      }}
                    >
                      Écrire à {otherClubForManager.name}
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          {!viewerIsTargetPlayer ? (
            <div className="flex items-center gap-2">
              <Avatar
                name={`${offer.player.first_name} ${offer.player.last_name}`}
                photoUrl={offer.player.photo}
                size={40}
              />
              <div className="min-w-0">
                <p className="truncate text-sm text-text">
                  {offer.player.first_name} {offer.player.last_name}
                </p>
                <p className="truncate text-xs text-text-muted">{offer.player.position_label}</p>
              </div>
              {onOpenPublicPlayer ? (
                <button
                  type="button"
                  className="ml-auto shrink-0 text-xs font-medium text-primary-text hover:underline"
                  onClick={() => onOpenPublicPlayer(offer.player.membership_id)}
                >
                  Voir la fiche publique
                </button>
              ) : null}
            </div>
          ) : null}

          <p className="text-sm text-text">{offer.message}</p>
          {offer.conditions ? <p className="text-sm text-text-muted">{offer.conditions}</p> : null}

          <TransferTimeline steps={timeline} />

          <p className="text-xs text-text-muted">
            Des frais d'adhésion à {offer.target_club.name} seront dus. Aucun frais de sortie n'est demandé par{" "}
            {offer.origin_club.name}.
          </p>

          {offer.status === "blocked_debt" && viewerIsTargetPlayer ? (
            <div className="rounded-md bg-status-danger-bg p-3 text-sm text-status-danger-fg">
              <p className="font-medium">Transfert bloqué</p>
              <p>
                Régularisez {offer.debt_amount} auprès de {offer.origin_club.name} pour obtenir votre quitus. Le
                transfert se fera automatiquement dès que votre solde sera à jour : vous n'aurez rien à confirmer.
              </p>
              {offer.debt_checked_at ? (
                <p className="mt-1 text-[13px]">
                  Montant mis à jour le {new Date(offer.debt_checked_at).toLocaleString("fr-FR")}.
                </p>
              ) : null}
            </div>
          ) : null}

          {offer.status === "completed" && viewerIsTargetPlayer ? (
            <p className="text-sm text-text">
              Vous avez rejoint {offer.target_club.name}
              {offer.completed_at ? ` le ${new Date(offer.completed_at).toLocaleDateString("fr-FR")}` : ""}.
            </p>
          ) : null}

          {responseError ? <p className="text-sm text-status-danger-fg">{responseError}</p> : null}
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmRefuse}
        title={`Refuser l'offre de ${offer.target_club.name} ?`}
        description={`${offer.target_club.name} sera prévenu.`}
        confirmLabel="Refuser l'offre"
        loading={responding}
        onConfirm={() => void handleRefuse()}
        onCancel={() => setConfirmRefuse(false)}
      />

      <ConfirmDialog
        open={confirmAccept}
        title={`Accepter l'offre de ${offer.target_club.name} ?`}
        description={
          <>
            Si vous êtes en ordre auprès de {offer.origin_club.name}, votre quitus sera établi et vous rejoindrez{" "}
            {offer.target_club.name} tout de suite. Sinon, le transfert sera bloqué jusqu'à ce que votre solde soit à
            jour, puis se fera automatiquement, sans nouvelle confirmation de votre part. Des frais d'adhésion à{" "}
            {offer.target_club.name} seront dus ; aucun frais de sortie.
          </>
        }
        confirmLabel="Accepter l'offre"
        danger={false}
        loading={responding}
        onConfirm={() => void handleAccept()}
        onCancel={() => setConfirmAccept(false)}
      />
    </>
  );
}
