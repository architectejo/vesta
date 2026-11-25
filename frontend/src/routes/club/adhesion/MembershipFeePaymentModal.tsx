import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getClubIdentity, recordMembershipFeePayment, type MembershipApplication } from "../../../api/clubs";
import { ApiError } from "../../../api/client";
import { CLIENT_UUID_CONFLICT_MESSAGE, useClientUuid } from "../../../hooks/useClientUuid";
import { Banner,ConfirmDialog, Modal, MoneyField, SegmentedControl, TextField, useToast } from "../../../design-system";
import { formatAmount, todayIsoDate, toApiAmount } from "../../treasury/money";
import { apiMessage, personName } from "./applicationText";

type Method = "cash" | "mobile_money" | "payment_link";

const METHODS: Array<{ value: Method; label: string }> = [
  { value: "cash", label: "Espèces" },
  { value: "mobile_money", label: "Mobile money" },
  { value: "payment_link", label: "Lien de paiement" },
];

/**
 * Modale « Frais d'adhésion de {nom} » (CDC 4.3 étape 2 ; Trésorier ou
 * adjoint, après confirmation). Le montant dû n'est pas fourni par l'API pour un
 * dossier : le Trésorier le saisit, l'API décide si les frais sont soldés
 * (génération de la fiche et notification du parrain).
 */
export function MembershipFeePaymentModal({
  application,
  level = 1,
  onClose,
  onDone,
}: {
  application: MembershipApplication;
  level?: 1 | 2;
  onClose: () => void;
  onDone: () => void;
}) {
  const { showToast } = useToast();
  const clientUuid = useClientUuid();
  const identityQuery = useQuery({ queryKey: ["club-identity"], queryFn: getClubIdentity });
  const currency = identityQuery.data?.currency ?? "";

  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<Method>("cash");
  const [reference, setReference] = useState("");
  const [paidOn, setPaidOn] = useState(todayIsoDate());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  function inputSignature(): string {
    return JSON.stringify([application.id, toApiAmount(amount), method, reference.trim(), paidOn]);
  }

  function handleConfirm(): void {
    const next: Record<string, string> = {};
    const numeric = Number(toApiAmount(amount));
    if (!amount || Number.isNaN(numeric) || numeric <= 0) next.amount = "Saisissez un montant supérieur à 0.";
    if (method !== "cash" && !reference.trim()) next.reference = "Indiquez la référence de la transaction.";
    if (!paidOn) next.paidOn = "Ce champ est obligatoire.";
    else if (paidOn > todayIsoDate()) next.paidOn = "La date ne peut pas être dans le futur.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    setError(null);
    clientUuid.get(inputSignature());
    setConfirmOpen(true);
  }

  async function submit(): Promise<void> {
    if (submitting) return;
    setSubmitting(true);
    try {
      await recordMembershipFeePayment({
        application_id: application.id,
        amount: toApiAmount(amount),
        method,
        paid_on: paidOn,
        reference: reference.trim(),
        client_uuid: clientUuid.get(inputSignature()),
      });
      clientUuid.reset();
      setConfirmOpen(false);
      showToast("Frais d'adhésion enregistrés.");
      onDone();
    } catch (err) {
      setConfirmOpen(false);
      setError(
        err instanceof ApiError && err.status === 409 && err.code === "client_uuid_conflict"
          ? CLIENT_UUID_CONFLICT_MESSAGE
          : apiMessage(err),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title={`Frais d'adhésion de ${personName(application.player)}`}
        size="md"
        level={level}
        isDirty={amount !== "" || reference !== ""}
        confirmLabel="Enregistrer"
        onConfirm={handleConfirm}
      >
        <div className="space-y-4">
          {error ? <Banner variant="danger">{error}</Banner> : null}
          <MoneyField label="Montant" currency={currency} value={amount} onChange={setAmount} error={errors.amount} />
          <SegmentedControl label="Mode" value={method} onChange={setMethod} options={METHODS} />
          {method !== "cash" ? (
            <TextField label="Référence" value={reference} onChange={setReference} error={errors.reference} />
          ) : null}
          <TextField
            label="Date"
            type="date"
            value={paidOn}
            onChange={setPaidOn}
            max={todayIsoDate()}
            error={errors.paidOn}
          />
          <p className="text-xs text-text-muted">
            Une fois les frais entièrement payés, la fiche d'adhésion est générée et le parrain est prévenu.
          </p>
        </div>
      </Modal>
      <ConfirmDialog
        open={confirmOpen}
        danger={false}
        title={`Valider ce paiement de ${formatAmount(toApiAmount(amount) || "0", currency)} ?`}
        description={`Les frais d'adhésion de ${personName(application.player)} seront enregistrés. Le paiement ne pourra plus être supprimé, seulement annulé.`}
        confirmLabel="Valider"
        loadingLabel="Validation…"
        loading={submitting}
        onConfirm={() => void submit()}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
