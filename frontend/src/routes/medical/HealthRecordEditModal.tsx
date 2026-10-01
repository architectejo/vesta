import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { updateHealthRecord, type BloodGroup, type HealthRecordFull } from "../../api/medical";
import { Modal, TextArea, TextField, useToast } from "../../design-system";

export interface HealthRecordEditModalProps {
  open: boolean;
  record: HealthRecordFull;
  onClose: () => void;
  onUpdated: () => void;
}

const BLOOD_GROUP_OPTIONS: Array<{ value: BloodGroup; label: string }> = [
  { value: "", label: "Non renseigné" },
  { value: "A+", label: "A+" },
  { value: "A-", label: "A-" },
  { value: "B+", label: "B+" },
  { value: "B-", label: "B-" },
  { value: "AB+", label: "AB+" },
  { value: "AB-", label: "AB-" },
  { value: "O+", label: "O+" },
  { value: "O-", label: "O-" },
];

const PHONE_PATTERN = /^[0-9+()\s.-]{6,30}$/;

/** « Modifier la fiche » (medical.md §4.5), Médecin, niveau 2. */
export function HealthRecordEditModal({ open, record, onClose, onUpdated }: HealthRecordEditModalProps) {
  const { showToast } = useToast();
  const [bloodGroup, setBloodGroup] = useState<BloodGroup>(record.blood_group);
  const [allergies, setAllergies] = useState(record.allergies);
  const [medicalHistory, setMedicalHistory] = useState(record.medical_history);
  const [ongoingTreatments, setOngoingTreatments] = useState(record.ongoing_treatments);
  const [contactName, setContactName] = useState(record.emergency_contact_name);
  const [contactPhone, setContactPhone] = useState(record.emergency_contact_phone);
  const [phoneError, setPhoneError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setBloodGroup(record.blood_group);
    setAllergies(record.allergies);
    setMedicalHistory(record.medical_history);
    setOngoingTreatments(record.ongoing_treatments);
    setContactName(record.emergency_contact_name);
    setContactPhone(record.emergency_contact_phone);
    setPhoneError(undefined);
    setSubmitError(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, record.membership_id]);

  async function handleSubmit(): Promise<void> {
    if (contactPhone.trim() && !PHONE_PATTERN.test(contactPhone.trim())) {
      setPhoneError("Numéro de téléphone invalide.");
      return;
    }
    setPhoneError(undefined);
    setSubmitting(true);
    setSubmitError(undefined);
    try {
      await updateHealthRecord(record.membership_id, {
        blood_group: bloodGroup,
        allergies,
        medical_history: medicalHistory,
        ongoing_treatments: ongoingTreatments,
        emergency_contact_name: contactName,
        emergency_contact_phone: contactPhone,
      });
      showToast("Fiche de santé mise à jour.");
      onUpdated();
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
      title="Modifier la fiche"
      size="md"
      level={2}
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <div className="rounded-md border border-border p-3 text-sm">
          <p className="font-medium text-text">Déclaration du joueur</p>
          <p className="mt-1 whitespace-pre-wrap text-text-muted">
            {record.self_declaration || "Le joueur n'a pas encore rempli sa déclaration."}
          </p>
        </div>

        <label className="block text-sm font-medium text-text">
          Groupe sanguin
          <select
            value={bloodGroup}
            onChange={(e) => setBloodGroup(e.target.value as BloodGroup)}
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text"
          >
            {BLOOD_GROUP_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <TextArea label="Allergies" optional value={allergies} onChange={setAllergies} />
        <TextArea label="Antécédents" optional value={medicalHistory} onChange={setMedicalHistory} />
        <TextArea label="Traitements en cours" optional value={ongoingTreatments} onChange={setOngoingTreatments} />
        <TextField label="Contact d'urgence : nom" optional value={contactName} onChange={setContactName} />
        <TextField
          label="Contact d'urgence : téléphone"
          optional
          type="tel"
          value={contactPhone}
          onChange={setContactPhone}
          error={phoneError}
        />

        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
