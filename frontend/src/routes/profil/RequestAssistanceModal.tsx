import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import {
  createSocialAssistanceRequest,
  getContributeInfo,
  getSocialAssistancePreview,
  type SocialAssistanceEventType,
} from "../../api/treasury";
import { Banner, Button, Modal, SegmentedControl, TextArea, TextField, useToast } from "../../design-system";
import { formatAmount, todayIsoDate } from "../treasury/money";

const EVENT_OPTIONS: Array<{ value: SocialAssistanceEventType; label: string }> = [
  { value: "birth", label: "Naissance" },
  { value: "marriage", label: "Mariage" },
  { value: "death", label: "Décès" },
];

export interface RequestAssistanceModalProps {
  open: boolean;
  onClose: () => void;
  onSubmitted?: () => void;
}

/**
 * Modale « Demander une assistance » (comptes-mon-profil.md §4.3 ; CDC 4.5.3,
 * 10.2 n° 33). Éligibilité, montant prévu, délai et montant à régulariser
 * viennent de `/treasury/social-assistance/preview/` : rien n'est calculé ici.
 * « Envoyer la demande » reste toujours actif, éligible ou non.
 */
export function RequestAssistanceModal({ open, onClose, onSubmitted }: RequestAssistanceModalProps) {
  const { showToast } = useToast();
  const [eventType, setEventType] = useState<SocialAssistanceEventType | null>(null);
  const [eventDate, setEventDate] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<{ type?: string; date?: string; description?: string; file?: string }>({});
  const [submitError, setSubmitError] = useState<string | undefined>();

  useEffect(() => {
    if (!open) {
      setEventType(null);
      setEventDate("");
      setDescription("");
      setFile(null);
      setErrors({});
      setSubmitError(undefined);
    }
  }, [open]);

  const dateInFuture = eventDate !== "" && eventDate > todayIsoDate();
  const previewEnabled = open && eventType !== null && eventDate !== "" && !dateInFuture;
  const previewQuery = useQuery({
    queryKey: ["treasury", "social-assistance-preview", eventType, eventDate],
    queryFn: () => getSocialAssistancePreview(eventType as SocialAssistanceEventType, eventDate),
    enabled: previewEnabled,
  });
  const contributeQuery = useQuery({
    queryKey: ["treasury", "contribute-info"],
    queryFn: getContributeInfo,
    enabled: open,
  });
  const paymentLink = contributeQuery.data?.payment_link_configured ? contributeQuery.data.payment_link_url : null;
  const preview = previewEnabled ? previewQuery.data : undefined;

  const mutation = useMutation({
    mutationFn: () =>
      createSocialAssistanceRequest({
        event_type: eventType as SocialAssistanceEventType,
        event_date: eventDate,
        description: description.trim(),
        attachment: file as File,
      }),
    onSuccess: (created) => {
      showToast(
        created.eligible_at_submission
          ? "Demande envoyée. Le Président et le Vice-président ont été prévenus."
          : "Demande envoyée. Le Président et le Vice-président ont été prévenus que vous n'étiez pas en ordre à la date de l'événement ; ils décideront au cas par cas.",
      );
      onSubmitted?.();
      onClose();
    },
    onError: (error) => {
      setSubmitError(
        error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.",
      );
    },
  });

  function submit(): void {
    const next: typeof errors = {};
    if (!eventType) next.type = "Choisissez un événement.";
    if (!eventDate) next.date = "Ce champ est obligatoire.";
    else if (dateInFuture) next.date = "La date ne peut pas être dans le futur.";
    if (!description.trim()) next.description = "Ce champ est obligatoire.";
    if (!file) next.file = "Joignez une pièce justificative.";
    setErrors(next);
    setSubmitError(undefined);
    if (Object.keys(next).length > 0) return;
    mutation.mutate();
  }

  const eligibility = preview?.eligibility;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Demander une assistance"
      size="md"
      isDirty={eventType !== null || eventDate !== "" || description !== "" || file !== null}
      isSubmitting={mutation.isPending}
      confirmLabel="Envoyer la demande"
      confirmLoadingLabel="Envoi…"
      onConfirm={submit}
    >
      <div className="space-y-4">
        {submitError ? <Banner variant="danger">{submitError}</Banner> : null}

        <SegmentedControl
          label="Événement"
          value={eventType}
          onChange={setEventType}
          options={EVENT_OPTIONS}
          error={errors.type}
        />
        <TextField
          label="Date de l'événement"
          type="date"
          max={todayIsoDate()}
          value={eventDate}
          onChange={setEventDate}
          error={errors.date}
        />

        {previewEnabled && previewQuery.isLoading ? (
          <p role="status" className="text-sm text-text-muted">
            Vérification de votre éligibilité…
          </p>
        ) : previewEnabled && previewQuery.isError ? (
          <Banner variant="danger">Impossible de vérifier votre éligibilité pour le moment.</Banner>
        ) : preview && eligibility ? (
          !preview.scale_configured ? (
            <Banner variant="warning">Aucun barème n'est configuré pour cet événement.</Banner>
          ) : eligibility.eligible ? (
            <Banner variant="success">
              Vous êtes éligible. Montant prévu : {formatAmount(preview.planned_amount ?? "0", eligibility.currency)}.
              Délai de traitement : {preview.processing_days} jours.
            </Banner>
          ) : (
            <Banner
              variant="warning"
              action={
                paymentLink ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => window.open(paymentLink, "_blank", "noopener,noreferrer")}
                  >
                    Contribuer
                  </Button>
                ) : undefined
              }
            >
              Vous n'étiez pas en ordre à cette date. Régularisez{" "}
              {formatAmount(eligibility.amount_to_regularize, eligibility.currency)} pour devenir éligible. Vous
              pouvez tout de même envoyer votre demande : le Président ou le Vice-président décidera au cas par cas.
              {preview.planned_amount
                ? ` Montant prévu : ${formatAmount(preview.planned_amount, eligibility.currency)}.`
                : ""}
            </Banner>
          )
        ) : null}

        <TextArea label="Description" value={description} onChange={setDescription} error={errors.description} />

        <div>
          <label htmlFor="assistance-attachment" className="mb-1 block text-sm font-medium text-text">
            Pièce justificative
          </label>
          <input
            id="assistance-attachment"
            type="file"
            accept=".jpg,.jpeg,.png,.webp,.pdf"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="block w-full text-sm text-text"
          />
          {errors.file ? <p className="mt-1 text-xs text-status-danger-fg">{errors.file}</p> : null}
        </div>
      </div>
    </Modal>
  );
}
