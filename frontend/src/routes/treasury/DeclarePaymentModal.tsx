import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { createPaymentDeclaration, getContributeInfo } from "../../api/treasury";
import { Banner, Modal, MoneyField, TextField, useToast } from "../../design-system";
import { toApiAmount } from "./money";

export interface DeclarePaymentModalProps {
  open: boolean;
  onClose: () => void;
  /** Après envoi : rafraîchit « Derniers paiements » du joueur. */
  onDeclared?: () => void;
}

/**
 * Modale « J'ai payé » (fiche comptes-mon-profil §4.2 ; CDC 4.6). Le joueur
 * déclare un paiement fait par le lien du club, pour lui-même : le serveur
 * déduit le joueur de la session. Types et devise viennent de l'API
 * (`/treasury/contribute/`). Un type de cotisation n'est pas un joueur : la
 * liste déroulante native est autorisée ici.
 */
export function DeclarePaymentModal({ open, onClose, onDeclared }: DeclarePaymentModalProps) {
  const { showToast } = useToast();
  const [typeId, setTypeId] = useState("");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<{ type?: string; amount?: string; reference?: string }>({});
  const [submitError, setSubmitError] = useState<string | undefined>();

  const infoQuery = useQuery({ queryKey: ["treasury", "contribute"], queryFn: getContributeInfo, enabled: open });
  const info = infoQuery.data;

  useEffect(() => {
    if (!open) {
      setTypeId("");
      setAmount("");
      setReference("");
      setFile(null);
      setErrors({});
      setSubmitError(undefined);
    }
  }, [open]);

  // Type par défaut : celui que l'API désigne (sa mensuelle).
  useEffect(() => {
    if (open && info && typeId === "" && info.default_contribution_type_id !== null) {
      setTypeId(String(info.default_contribution_type_id));
    }
  }, [open, info, typeId]);

  const mutation = useMutation({
    mutationFn: () =>
      createPaymentDeclaration({
        contribution_type_id: Number(typeId),
        amount: toApiAmount(amount.trim()),
        reference: reference.trim(),
        attachment: file,
      }),
    onSuccess: () => {
      showToast("Déclaration envoyée. Le trésorier la validera.");
      onDeclared?.();
      onClose();
    },
    onError: (error) => {
      setSubmitError(error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    },
  });

  function submit(): void {
    const next: typeof errors = {};
    if (!typeId) next.type = "Choisissez un type de cotisation.";
    const value = Number(toApiAmount(amount.trim()));
    if (!amount.trim() || Number.isNaN(value) || value <= 0) next.amount = "Saisissez un montant supérieur à 0.";
    if (!reference.trim()) next.reference = "Indiquez la référence reçue lors du paiement.";
    setErrors(next);
    setSubmitError(undefined);
    if (Object.keys(next).length > 0) return;
    mutation.mutate();
  }

  const dirty = amount !== "" || reference !== "" || file !== null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="J'ai payé"
      size="md"
      loading={infoQuery.isLoading}
      isDirty={dirty}
      isSubmitting={mutation.isPending}
      confirmLabel="Envoyer la déclaration"
      confirmLoadingLabel="Envoi…"
      confirmDisabled={!info}
      onConfirm={submit}
    >
      {infoQuery.isError ? (
        <p role="alert" className="text-sm text-status-danger-fg">
          Impossible de charger vos types de cotisation. Réessayez.
        </p>
      ) : info ? (
        <div className="space-y-4">
          <p className="text-sm text-text-muted">
            Déclarez ici un paiement fait par le lien du club. Le trésorier le vérifiera avant de l'ajouter à votre solde.
          </p>
          {submitError ? <Banner variant="danger">{submitError}</Banner> : null}

          <label className="block text-sm font-medium text-text">
            Type de cotisation
            <select
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
              value={typeId}
              onChange={(event) => setTypeId(event.target.value)}
            >
              <option value="" disabled>
                Choisissez un type
              </option>
              {info.contribution_types.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.name}
                </option>
              ))}
            </select>
            {errors.type ? <span className="mt-1 block text-xs text-status-danger-fg">{errors.type}</span> : null}
          </label>

          <MoneyField label="Montant" currency={info.currency} value={amount} onChange={setAmount} error={errors.amount} />
          <TextField
            label="Référence de transaction"
            value={reference}
            onChange={setReference}
            error={errors.reference}
          />

          <div>
            <label htmlFor="declaration-capture" className="mb-1 block text-sm font-medium text-text">
              Capture du paiement (facultatif)
            </label>
            <input
              id="declaration-capture"
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="block w-full text-sm text-text"
            />
          </div>
        </div>
      ) : null}
    </Modal>
  );
}
