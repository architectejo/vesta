import { useState } from "react";
import { createIncident, type IncidentCause, type IncidentType } from "../../api/sport";
import { ApiError } from "../../api/client";
import { searchActiveClubPlayers } from "../../api/clubs";
import {
  Modal,
  NumberField,
  PlayerSearch,
  SegmentedControl,
  TextArea,
  TextField,
  type PlayerSearchResult,
} from "../../design-system";

const CAUSE_OPTIONS: Array<{ value: IncidentCause; label: string }> = [
  { value: "contestation", label: "Contestation" },
  { value: "serious_foul", label: "Faute grossière" },
  { value: "behaviour", label: "Comportement" },
  { value: "lateness", label: "Retard" },
  { value: "other", label: "Autre" },
];

export interface IncidentModalProps {
  open: boolean;
  eventId: number;
  onClose: () => void;
  onCreated: () => void;
}

/**
 * « Signaler un incident » (CDC 4.9), champs repris directement du
 * contrat `IncidentCreateSerializer` (backend/apps/sport/serializers.py) :
 * la spec détaillée de cette modale vit dans `sport-espace-coach.md`
 * §4.5, hors du périmètre de la tâche 3.7 — ce formulaire suit fidèlement
 * le contrat d'API vérifié plutôt que d'inventer une mise en page.
 */
export function IncidentModal({ open, eventId, onClose, onCreated }: IncidentModalProps) {
  const [player, setPlayer] = useState<PlayerSearchResult | null>(null);
  const [incidentType, setIncidentType] = useState<IncidentType>("yellow_card");
  const [cause, setCause] = useState<IncidentCause>("serious_foul");
  const [causeDetail, setCauseDetail] = useState("");
  const [issuedBy, setIssuedBy] = useState("");
  const [minute, setMinute] = useState<number | null>(null);
  const [playerError, setPlayerError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);

  function reset(): void {
    setPlayer(null);
    setIncidentType("yellow_card");
    setCause("serious_foul");
    setCauseDetail("");
    setIssuedBy("");
    setMinute(null);
    setPlayerError(undefined);
    setSubmitError(undefined);
  }

  async function handleSubmit(): Promise<void> {
    if (!player) {
      setPlayerError("Choisissez un joueur.");
      return;
    }
    setPlayerError(undefined);
    setSubmitError(undefined);
    setSubmitting(true);
    try {
      await createIncident(eventId, {
        membership_id: Number(player.id),
        incident_type: incidentType,
        cause,
        cause_detail: causeDetail,
        issued_by: issuedBy,
        minute,
      });
      reset();
      onCreated();
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.detail : "Une erreur est survenue. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="Signaler un incident"
      size="md"
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-text">Joueur</label>
          <PlayerSearch value={player} onChange={setPlayer} searchPlayers={searchActiveClubPlayers} />
          {playerError ? <p className="mt-1 text-xs text-status-danger-fg">{playerError}</p> : null}
        </div>

        <SegmentedControl
          label="Type"
          value={incidentType}
          onChange={setIncidentType}
          options={[
            { value: "yellow_card", label: "Carton jaune" },
            { value: "red_card", label: "Carton rouge" },
            { value: "internal_sanction", label: "Sanction interne" },
          ]}
        />

        <label className="block text-sm font-medium text-text">
          Cause
          <select
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
            value={cause}
            onChange={(e) => setCause(e.target.value as IncidentCause)}
          >
            {CAUSE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <TextArea label="Précision" optional value={causeDetail} onChange={setCauseDetail} rows={2} />
        <TextField label="Arbitre ou auteur de la sanction" optional value={issuedBy} onChange={setIssuedBy} />
        <NumberField label="Minute" optional value={minute} onChange={setMinute} min={0} max={130} />

        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
