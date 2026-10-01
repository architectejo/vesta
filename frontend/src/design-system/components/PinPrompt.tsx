import { useEffect, useRef, useState, type ReactNode } from "react";
import { Modal } from "./Modal";

const MIN_PIN_DIGITS = 4;
const MAX_PIN_DIGITS = 6;

export interface PinPromptProps {
  open: boolean;
  /** Défaut : « Confirmer avec votre code PIN » (docs/lot0/design-system.md §3.1). */
  title?: string;
  /** Rappel de l'action en une ligne (« Valider le paiement de {montant} pour {nom} »). */
  description: ReactNode;
  confirmLabel?: string;
  confirmLoadingLabel?: string;
  isSubmitting?: boolean;
  /** Message d'erreur déjà traduit (voir `pinErrors.ts`). */
  error?: string;
  /** Désactive la confirmation (ex. hors connexion) sans toucher à la saisie. */
  disabled?: boolean;
  onSubmit: (pin: string) => void;
  onClose: () => void;
}

/**
 * Confirmation d'une action sensible par code PIN (docs/lot0/design-system.md
 * §3.1 « PinPrompt » ; CDC 7.2). Le PIN n'est jamais vérifié ni stocké côté
 * interface : il est simplement transmis à l'appel API fourni par l'appelant.
 */
export function PinPrompt({
  open,
  title = "Confirmer avec votre code PIN",
  description,
  confirmLabel = "Confirmer",
  confirmLoadingLabel = "Vérification…",
  isSubmitting = false,
  error,
  disabled = false,
  onSubmit,
  onClose,
}: PinPromptProps) {
  const [pin, setPin] = useState("");
  const autoSubmittedRef = useRef(false);

  useEffect(() => {
    if (!open) {
      setPin("");
      autoSubmittedRef.current = false;
    }
  }, [open]);

  // Une erreur (PIN incorrect, verrouillage…) efface la saisie pour que le
  // joueur retape son code plutôt que de rejouer silencieusement le même.
  useEffect(() => {
    if (error) {
      setPin("");
      autoSubmittedRef.current = false;
    }
  }, [error]);

  useEffect(() => {
    if (pin.length < MAX_PIN_DIGITS) {
      autoSubmittedRef.current = false;
      return;
    }
    if (autoSubmittedRef.current || isSubmitting || disabled) return;
    autoSubmittedRef.current = true;
    onSubmit(pin);
    // onSubmit est fourni par l'appelant (appel API) : ne pas le placer dans
    // les dépendances évite un ré-arm au changement de référence de fonction.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pin, isSubmitting, disabled]);

  const canConfirm =
    pin.length >= MIN_PIN_DIGITS && pin.length <= MAX_PIN_DIGITS && !isSubmitting && !disabled;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      level={2}
      isSubmitting={isSubmitting}
      confirmLabel={confirmLabel}
      confirmLoadingLabel={confirmLoadingLabel}
      confirmDisabled={!canConfirm}
      onConfirm={() => onSubmit(pin)}
    >
      <div className="space-y-3">
        <p className="text-sm text-text">{description}</p>
        <div>
          <label htmlFor="pin-prompt-input" className="mb-1 block text-sm font-medium text-text">
            Votre code PIN
          </label>
          <input
            id="pin-prompt-input"
            type="password"
            inputMode="numeric"
            autoComplete="off"
            autoFocus
            disabled={isSubmitting}
            value={pin}
            onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, MAX_PIN_DIGITS))}
            aria-invalid={Boolean(error) || undefined}
            aria-describedby={error ? "pin-prompt-error" : undefined}
            className="h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-center text-lg tracking-[0.5em] text-text disabled:opacity-60"
          />
        </div>
        {error ? (
          <p id="pin-prompt-error" role="alert" className="text-xs text-status-danger-fg">
            {error}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}
