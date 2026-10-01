import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import {
  completeInjury,
  type InjuryDetail,
  type InjuryReferral,
  type InjurySeverity,
} from "../../api/medical";
import { Banner, Modal, NumberField, SegmentedControl, TextArea, TextField, useToast } from "../../design-system";
import { formatDateFrLong, formatTimeFr } from "./medicalFormat";
import { injuryEventLabel } from "./medicalLabels";

export interface InjuryCompleteModalProps {
  open: boolean;
  injury: InjuryDetail;
  playerName: string;
  /** Consentement au traitement des données de santé du joueur manquant
   * (medical.md §4.2, §4.7) : bloque l'enregistrement (bandeau à la place
   * du bouton), déjà revérifié côté API en défense en profondeur. */
  consentMissing: boolean;
  onClose: () => void;
  onCompleted: () => void;
}

const SEVERITY_OPTIONS: Array<{ value: InjurySeverity; label: string }> = [
  { value: "mild", label: "Légère" },
  { value: "moderate", label: "Modérée" },
  { value: "severe", label: "Grave" },
];

const REFERRAL_OPTIONS: Array<{ value: InjuryReferral; label: string }> = [
  { value: "rest", label: "Repos" },
  { value: "consultation", label: "Consultation" },
  { value: "hospital", label: "Hôpital" },
];

function addDays(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

/**
 * « Compléter la blessure » / « Modifier le bilan » (medical.md §4.7, CDC
 * 4.12 étape 2), Médecin.
 */
export function InjuryCompleteModal({
  open,
  injury,
  playerName,
  consentMissing,
  onClose,
  onCompleted,
}: InjuryCompleteModalProps) {
  const { showToast } = useToast();
  const isEdit = injury.doctor_completed_at !== null;
  const injuryDate = injury.reported_at.slice(0, 10);

  const [location, setLocation] = useState(injury.location_on_body);
  const [severity, setSeverity] = useState<InjurySeverity | null>(injury.severity || null);
  const [onSiteCare, setOnSiteCare] = useState(injury.on_site_care);
  const [referral, setReferral] = useState<InjuryReferral | null>(injury.referral || null);
  const [daysOut, setDaysOut] = useState<number | null>(injury.estimated_days_out);
  const [returnDate, setReturnDate] = useState("");
  const [dateTouched, setDateTouched] = useState(false);
  const [errors, setErrors] = useState<{ location?: string; severity?: string; referral?: string; returnDate?: string }>({});
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLocation(injury.location_on_body);
    setSeverity((injury.severity || null) as InjurySeverity | null);
    setOnSiteCare(injury.on_site_care);
    setReferral((injury.referral || null) as InjuryReferral | null);
    setDaysOut(injury.estimated_days_out);
    setReturnDate("");
    setDateTouched(false);
    setErrors({});
    setSubmitError(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, injury.id]);

  useEffect(() => {
    if (!dateTouched && daysOut != null) {
      setReturnDate(addDays(injuryDate, daysOut));
    }
  }, [daysOut, dateTouched, injuryDate]);

  function validate(): boolean {
    const next: typeof errors = {};
    if (!location.trim()) next.location = "Indiquez la localisation.";
    if (!severity) next.severity = "Choisissez la gravité.";
    if (!referral) next.referral = "Choisissez une orientation.";
    if (returnDate && returnDate < injuryDate) next.returnDate = "La date de retour ne peut pas être avant la blessure.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(): Promise<void> {
    if (!validate()) return;
    setSubmitting(true);
    setSubmitError(undefined);
    try {
      await completeInjury(injury.id, {
        location_on_body: location.trim(),
        severity: severity ?? "",
        on_site_care: onSiteCare,
        referral: referral ?? "",
        estimated_days_out: daysOut,
        fitness_return_date: returnDate || null,
      });
      showToast(isEdit ? "Bilan mis à jour." : "Blessure complétée.");
      onCompleted();
      onClose();
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? "Modifier le bilan" : "Compléter la blessure"}
      size="md"
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      onConfirm={consentMissing ? undefined : () => void handleSubmit()}
      hideFooter={consentMissing}
    >
      <div className="space-y-4">
        <div className="space-y-1 rounded-md border border-border p-3 text-sm">
          <p className="font-medium text-text">{playerName}</p>
          <p className="text-text-muted">
            {formatDateFrLong(injury.reported_at)}
            {injury.occurred_time ? ` à ${formatTimeFr(injury.reported_at)}` : ""} ·{" "}
            {injuryEventLabel(injury)}
          </p>
          <p className="text-text">{injury.circumstances}</p>
        </div>

        {consentMissing ? (
          <Banner variant="warning">
            Vous pouvez fixer l'aptitude et suivre les blessures déclarées, mais pas compléter la fiche tant que le
            joueur n'a pas donné son consentement au traitement de ses données de santé.
          </Banner>
        ) : (
          <>
            <TextField
              label="Localisation"
              value={location}
              onChange={setLocation}
              placeholder="Ex. cheville droite"
              error={errors.location}
            />
            <SegmentedControl
              label="Gravité"
              value={severity}
              onChange={setSeverity}
              options={SEVERITY_OPTIONS}
              error={errors.severity}
            />
            <TextArea label="Soins donnés sur place" optional value={onSiteCare} onChange={setOnSiteCare} />
            <SegmentedControl
              label="Orientation"
              value={referral}
              onChange={setReferral}
              options={REFERRAL_OPTIONS}
              error={errors.referral}
            />
            <NumberField
              label="Durée d'indisponibilité estimée (jours)"
              optional
              value={daysOut}
              onChange={setDaysOut}
              min={0}
              max={365}
            />
            <label className="block text-sm font-medium text-text">
              Date de retour prévue <span className="font-normal text-text-muted">(facultatif)</span>
              <input
                type="date"
                value={returnDate}
                onChange={(e) => {
                  setDateTouched(true);
                  setReturnDate(e.target.value);
                }}
                className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text"
              />
              <p className="mt-1 text-xs text-text-muted">
                Seules l'aptitude et cette date sont visibles par le Coach et le Président.
              </p>
              {errors.returnDate ? <p className="mt-1 text-xs text-status-danger-fg">{errors.returnDate}</p> : null}
            </label>

            {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
          </>
        )}
      </div>
    </Modal>
  );
}
