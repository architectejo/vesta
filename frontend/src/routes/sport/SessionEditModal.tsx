import { useState } from "react";
import { updateSession, type SessionDetail, type SessionInput } from "../../api/sport";
import { ApiError } from "../../api/client";
import { Modal, TextArea, TextField } from "../../design-system";

export interface SessionEditModalProps {
  open: boolean;
  session: SessionDetail;
  onClose: () => void;
  onUpdated: () => void;
}

/**
 * « Modifier la séance » (docs/ecrans/sport-seance.md §4.2), mêmes champs
 * que « Créer une séance » (`sport-espace-coach.md` §4.1, hors périmètre
 * de cette tâche) : le formulaire suit le contrat `SessionUpdateSerializer`.
 */
export function SessionEditModal({ open, session, onClose, onUpdated }: SessionEditModalProps) {
  const [eventDate, setEventDate] = useState(session.event_date);
  const [gatheringTime, setGatheringTime] = useState(session.gathering_time.slice(0, 5));
  const [cutoff, setCutoff] = useState(session.late_arrival_cutoff.slice(0, 5));
  const [location, setLocation] = useState(session.location);
  const [teamAColor, setTeamAColor] = useState(session.team_a_color || "#1d4ed8");
  const [teamBColor, setTeamBColor] = useState(session.team_b_color || "#dc2626");
  const [instructions, setInstructions] = useState(session.instructions);
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(): Promise<void> {
    setError(undefined);
    setSubmitting(true);
    const input: SessionInput = {
      event_date: eventDate,
      gathering_time: gatheringTime,
      late_arrival_cutoff: cutoff,
      location,
      team_a_color: teamAColor,
      team_b_color: teamBColor,
      instructions,
    };
    try {
      await updateSession(session.id, input);
      onUpdated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Modifier la séance"
      size="md"
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <label className="block text-sm font-medium text-text">
          Date
          <input
            type="date"
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
            value={eventDate}
            onChange={(e) => setEventDate(e.target.value)}
          />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm font-medium text-text">
            Rassemblement
            <input
              type="time"
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
              value={gatheringTime}
              onChange={(e) => setGatheringTime(e.target.value)}
            />
          </label>
          <label className="block text-sm font-medium text-text">
            Limite d'arrivée
            <input
              type="time"
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
              value={cutoff}
              onChange={(e) => setCutoff(e.target.value)}
            />
          </label>
        </div>
        <TextField label="Terrain" optional value={location} onChange={setLocation} />
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm font-medium text-text">
            Couleur équipe A
            <input
              type="color"
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-2"
              value={teamAColor}
              onChange={(e) => setTeamAColor(e.target.value)}
            />
          </label>
          <label className="block text-sm font-medium text-text">
            Couleur équipe B
            <input
              type="color"
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-2"
              value={teamBColor}
              onChange={(e) => setTeamBColor(e.target.value)}
            />
          </label>
        </div>
        <TextArea label="Consignes" optional value={instructions} onChange={setInstructions} rows={3} />
        {error ? <p className="text-sm text-status-danger-fg">{error}</p> : null}
      </div>
    </Modal>
  );
}
