import { useState } from "react";
import { createSession, type SessionInput } from "../../api/sport";
import { ApiError } from "../../api/client";
import { Modal, TextArea, TextField } from "../../design-system";
import { todayIsoDate } from "./sportTime";

export interface CreateSessionModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

/**
 * « Créer une séance » (`docs/ecrans/sport-espace-coach.md` §4.1), ouverte
 * ici depuis l'état vide du Vestiaire du jour (`sport-vestiaire.md` §6,
 * ligne « Aucun événement aujourd'hui »), seul point d'entrée existant
 * aujourd'hui dans l'interface : la page « Espace coach » elle-même n'est
 * pas encore implémentée. Mêmes champs que `SessionEditModal` (« Modifier
 * la séance »), avec en plus les validations de création listées au
 * tableau du §4.1 (date non passée, ordre des heures, couleurs distinctes)
 * qu'un formulaire de modification n'a pas besoin d'imposer à l'identique.
 */
export function CreateSessionModal({ open, onClose, onCreated }: CreateSessionModalProps) {
  const [eventDate, setEventDate] = useState(todayIsoDate());
  const [gatheringTime, setGatheringTime] = useState("");
  const [cutoff, setCutoff] = useState("");
  const [location, setLocation] = useState("");
  const [teamAColor, setTeamAColor] = useState("#1d4ed8");
  const [teamBColor, setTeamBColor] = useState("#dc2626");
  const [instructions, setInstructions] = useState("");

  const [dateError, setDateError] = useState<string | undefined>(undefined);
  const [gatheringError, setGatheringError] = useState<string | undefined>(undefined);
  const [cutoffError, setCutoffError] = useState<string | undefined>(undefined);
  const [colorError, setColorError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  function reset(): void {
    setEventDate(todayIsoDate());
    setGatheringTime("");
    setCutoff("");
    setLocation("");
    setTeamAColor("#1d4ed8");
    setTeamBColor("#dc2626");
    setInstructions("");
    setDateError(undefined);
    setGatheringError(undefined);
    setCutoffError(undefined);
    setColorError(undefined);
    setSubmitError(undefined);
  }

  function validate(): boolean {
    let ok = true;
    if (!eventDate || eventDate < todayIsoDate()) {
      setDateError("La date ne peut pas être passée.");
      ok = false;
    } else {
      setDateError(undefined);
    }
    if (!gatheringTime) {
      setGatheringError("Ce champ est obligatoire.");
      ok = false;
    } else {
      setGatheringError(undefined);
    }
    if (!cutoff) {
      setCutoffError("Ce champ est obligatoire.");
      ok = false;
    } else if (gatheringTime && cutoff < gatheringTime) {
      setCutoffError("L'heure limite doit être égale ou postérieure à l'heure de rassemblement.");
      ok = false;
    } else {
      setCutoffError(undefined);
    }
    if (teamAColor === teamBColor) {
      setColorError("Les deux équipes doivent avoir des couleurs différentes.");
      ok = false;
    } else {
      setColorError(undefined);
    }
    return ok;
  }

  async function handleSubmit(): Promise<void> {
    setSubmitError(undefined);
    if (!validate()) return;
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
      await createSession(input);
      reset();
      onCreated();
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : "Une erreur est survenue. Réessayez.");
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
      title="Créer une séance"
      size="md"
      isSubmitting={submitting}
      confirmLabel="Créer la séance"
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
          {dateError ? <p className="mt-1 text-xs text-status-danger-fg">{dateError}</p> : null}
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
            {gatheringError ? <p className="mt-1 text-xs text-status-danger-fg">{gatheringError}</p> : null}
          </label>
          <label className="block text-sm font-medium text-text">
            Limite d'arrivée
            <input
              type="time"
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
              value={cutoff}
              onChange={(e) => setCutoff(e.target.value)}
            />
            {cutoffError ? <p className="mt-1 text-xs text-status-danger-fg">{cutoffError}</p> : null}
          </label>
        </div>
        <TextField label="Terrain" optional value={location} onChange={setLocation} maxLength={120} />
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm font-medium text-text">
            Maillots équipe A
            <input
              type="color"
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-2"
              value={teamAColor}
              onChange={(e) => setTeamAColor(e.target.value)}
            />
          </label>
          <label className="block text-sm font-medium text-text">
            Maillots équipe B
            <input
              type="color"
              className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-2"
              value={teamBColor}
              onChange={(e) => setTeamBColor(e.target.value)}
            />
          </label>
        </div>
        {colorError ? <p className="text-xs text-status-danger-fg">{colorError}</p> : null}
        <TextArea label="Consignes" optional value={instructions} onChange={setInstructions} rows={3} maxLength={1000} />
        {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
      </div>
    </Modal>
  );
}
