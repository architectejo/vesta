import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { createOffer } from "../../api/mercato";
import { Modal, PlayerSearch, TextArea, type PlayerSearchResult } from "../../design-system";
import { searchMarketPlayers } from "./mercatoSearches";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

export interface FaireUneOffreModalProps {
  open: boolean;
  /** Prérempli si la modale vient de la fiche publique (§4.2). */
  initialPlayer?: PlayerSearchResult | null;
  ownClubName: string;
  onClose: () => void;
  onSent: (playerName: string) => void;
}

/** « Faire une offre » (fiche `mercato.md` §4.2, Président/DS). */
export function FaireUneOffreModal({ open, initialPlayer, ownClubName, onClose, onSent }: FaireUneOffreModalProps) {
  const [player, setPlayer] = useState<PlayerSearchResult | null>(initialPlayer ?? null);
  const [message, setMessage] = useState("");
  const [conditions, setConditions] = useState("");
  const [playerError, setPlayerError] = useState<string | undefined>(undefined);
  const [messageError, setMessageError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPlayer(initialPlayer ?? null);
    setMessage("");
    setConditions("");
    setPlayerError(undefined);
    setMessageError(undefined);
    setSubmitError(undefined);
  }, [open, initialPlayer]);

  async function handleSubmit(): Promise<void> {
    let hasError = false;
    if (!player) {
      setPlayerError("Choisissez un joueur.");
      hasError = true;
    } else {
      setPlayerError(undefined);
    }
    if (!message.trim()) {
      setMessageError("Ce champ est obligatoire.");
      hasError = true;
    } else {
      setMessageError(undefined);
    }
    if (hasError || !player) return;

    setSubmitting(true);
    setSubmitError(undefined);
    try {
      await createOffer({
        target_membership_id: Number(player.id),
        message: message.trim(),
        conditions: conditions.trim() || undefined,
      });
      onSent(`${player.firstName} ${player.lastName}`);
    } catch (error) {
      setSubmitError(apiErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  const isDirty = Boolean(player || message.trim() || conditions.trim());

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Faire une offre"
      size="md"
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Envoyer l'offre"
      confirmLoadingLabel="Envoi…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <div>
          <p className="mb-1 text-sm font-medium text-text">Joueur visé</p>
          <PlayerSearch
            value={player}
            onChange={setPlayer}
            searchPlayers={searchMarketPlayers}
            placeholder="Nom du joueur"
          />
          {playerError ? <p className="mt-1 text-xs text-status-danger-fg">{playerError}</p> : null}
        </div>
        <TextArea
          label="Message"
          value={message}
          onChange={setMessage}
          maxLength={1000}
          showCount
          error={messageError}
        />
        <TextArea
          label="Conditions"
          optional
          value={conditions}
          onChange={setConditions}
          maxLength={1000}
          showCount
          help="Par exemple : poste envisagé, date d'arrivée souhaitée."
        />
        {player ? (
          <div className="rounded-md bg-surface-muted p-3 text-sm text-text">
            {player.firstName} et son club actuel seront prévenus. S'il accepte, Vesta vérifie qu'il est en ordre
            auprès de son club actuel : le quitus est alors établi et le transfert se fait automatiquement. Des frais
            d'adhésion à {ownClubName} seront dus. Aucun frais de sortie n'est demandé par son club actuel.
          </div>
        ) : null}
        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
