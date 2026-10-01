import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { createThread } from "../../api/mercato";
import { ClubSearch, Modal, TextArea, TextField, type ClubSearchResult } from "../../design-system";
import { searchClubsFromMarket } from "./mercatoSearches";

export interface EcrireAUnClubModalProps {
  open: boolean;
  /** Prérempli et verrouillé si la modale vient d'une fiche ou d'une offre (§4.5). */
  lockedClub?: ClubSearchResult | null;
  /** Puce « À propos de l'offre pour {joueur} » si la modale vient d'une offre. */
  aboutOfferPlayerName?: string;
  transferOfferId?: number | null;
  onClose: () => void;
  onSent: (clubName: string) => void;
}

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

/** « Écrire à un club » (fiche `mercato.md` §4.5, Président/DS). */
export function EcrireAUnClubModal({
  open,
  lockedClub,
  aboutOfferPlayerName,
  transferOfferId,
  onClose,
  onSent,
}: EcrireAUnClubModalProps) {
  const [club, setClub] = useState<ClubSearchResult | null>(lockedClub ?? null);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [clubError, setClubError] = useState<string | undefined>(undefined);
  const [messageError, setMessageError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setClub(lockedClub ?? null);
    setSubject("");
    setMessage("");
    setClubError(undefined);
    setMessageError(undefined);
    setSubmitError(undefined);
  }, [open, lockedClub]);

  async function handleSubmit(): Promise<void> {
    let hasError = false;
    if (!club) {
      setClubError("Choisissez un club.");
      hasError = true;
    } else {
      setClubError(undefined);
    }
    if (!message.trim()) {
      setMessageError("Ce champ est obligatoire.");
      hasError = true;
    } else {
      setMessageError(undefined);
    }
    if (hasError || !club) return;

    setSubmitting(true);
    setSubmitError(undefined);
    try {
      await createThread({
        club_id: Number(club.id),
        subject: subject.trim() || undefined,
        message: message.trim(),
        transfer_offer_id: transferOfferId ?? undefined,
      });
      onSent(club.name);
    } catch (error) {
      setSubmitError(apiErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  const isDirty = Boolean((!lockedClub && club) || subject.trim() || message.trim());

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Écrire à un club"
      size="md"
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Envoyer"
      confirmLoadingLabel="Envoi…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        {aboutOfferPlayerName ? (
          <p className="inline-flex rounded-full bg-surface-muted px-2 py-1 text-xs text-text-muted">
            À propos de l'offre pour {aboutOfferPlayerName}
          </p>
        ) : null}
        <div>
          <p className="mb-1 text-sm font-medium text-text">Club</p>
          <ClubSearch value={club} onChange={setClub} searchClubs={searchClubsFromMarket} error={clubError} disabled={Boolean(lockedClub)} />
          {club ? (
            <p className="mt-1 text-xs text-text-muted">
              Le Président et le Directeur sportif de {club.name} recevront votre message.
            </p>
          ) : null}
        </div>
        <TextField label="Objet" optional value={subject} onChange={setSubject} maxLength={160} />
        <TextArea label="Message" value={message} onChange={setMessage} maxLength={2000} showCount error={messageError} />
        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
