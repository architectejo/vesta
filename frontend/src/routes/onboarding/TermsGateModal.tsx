import { useState } from "react";
import { acceptTerms } from "../../api/auth";
import type { TermsVersion } from "../../api/auth";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { Banner, Checkbox, Modal, useToast } from "../../design-system";

/**
 * Modale bloquante « Vos données et votre consentement » (club-accueil.md
 * §3 étape 2 ; CDC 7.5, 10.2 n°27).
 *
 * Point ouvert signalé au compte rendu : le schéma de données et l'API
 * (`apps.accounts.views.AcceptTermsView`) ne tracent qu'une seule
 * acceptation (`TermsAcceptance`, une version des CGU). La spec évoque
 * aussi des cases distinctes de consentement au traitement des données de
 * santé et à la publication de la carte de joueur (7.5) : aucun champ ni
 * endpoint ne les porte pour l'instant côté API. Cette modale ne couvre
 * donc que l'acceptation des CGU et de la politique de confidentialité,
 * seule brique réellement disponible dans ce lot.
 */
export function TermsGateModal({
  terms,
  onAccepted,
}: {
  terms: TermsVersion;
  onAccepted: () => void;
}) {
  const { logout } = useAuth();
  const { showToast } = useToast();
  const [accepted, setAccepted] = useState(false);
  const [showText, setShowText] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(): Promise<void> {
    if (!accepted) {
      setError("Vous devez accepter les conditions générales pour continuer.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await acceptTerms(terms.id);
      showToast("Conditions générales acceptées.");
      onAccepted();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setSubmitting(false);
    }
  }

  if (showText) {
    return (
      <Modal
        open
        onClose={() => setShowText(false)}
        title={`Conditions générales d'utilisation — version ${terms.version_number}`}
        size="lg"
        hideFooter
      >
        <p className="whitespace-pre-wrap text-sm text-text">{terms.content}</p>
      </Modal>
    );
  }

  return (
    <Modal
      open
      onClose={() => {
        void logout();
      }}
      blocking
      title="Vos données et votre consentement"
      size="md"
      isSubmitting={submitting}
      confirmLabel="Continuer"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        {error ? <Banner variant="danger">{error}</Banner> : null}
        <Checkbox
          checked={accepted}
          onChange={setAccepted}
          label={
            <>
              J'accepte les conditions générales d'utilisation et la politique de
              confidentialité de Vesta (version {terms.version_number}).{" "}
              <button
                type="button"
                onClick={() => setShowText(true)}
                className="font-medium text-primary-text hover:underline"
              >
                Lire les conditions générales
              </button>
            </>
          }
        />
      </div>
    </Modal>
  );
}
