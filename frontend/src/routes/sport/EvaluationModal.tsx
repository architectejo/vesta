import { useState } from "react";
import { createEvaluation } from "../../api/sport";
import { ApiError } from "../../api/client";
import { searchActiveClubPlayers } from "../../api/clubs";
import { Checkbox, Modal, NumberField, PlayerSearch, TextArea, type PlayerSearchResult } from "../../design-system";

export interface EvaluationModalProps {
  open: boolean;
  eventId: number;
  onClose: () => void;
  onCreated: () => void;
}

/**
 * « Évaluer les joueurs » (CDC 4.10 ; matrice 2.4, Coach/Président/VP
 * uniquement). Champs repris du contrat `EvaluationCreateSerializer` — la
 * mise en page détaillée de cette modale vit dans `sport-espace-coach.md`
 * §4.6, hors périmètre de la tâche 3.7.
 */
export function EvaluationModal({ open, eventId, onClose, onCreated }: EvaluationModalProps) {
  const [player, setPlayer] = useState<PlayerSearchResult | null>(null);
  const [overall, setOverall] = useState<number | null>(null);
  const [technical, setTechnical] = useState<number | null>(null);
  const [physical, setPhysical] = useState<number | null>(null);
  const [tactical, setTactical] = useState<number | null>(null);
  const [mental, setMental] = useState<number | null>(null);
  const [attitude, setAttitude] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [visibleToPlayer, setVisibleToPlayer] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  function reset(): void {
    setPlayer(null);
    setOverall(null);
    setTechnical(null);
    setPhysical(null);
    setTactical(null);
    setMental(null);
    setAttitude(null);
    setComment("");
    setVisibleToPlayer(false);
    setError(undefined);
  }

  async function handleSubmit(): Promise<void> {
    if (!player) {
      setError("Choisissez un joueur.");
      return;
    }
    if (overall == null) {
      setError("Donnez une note globale (0 à 10).");
      return;
    }
    setError(undefined);
    setSubmitting(true);
    try {
      await createEvaluation(eventId, {
        membership_id: Number(player.id),
        overall_score: String(overall),
        technical_score: technical != null ? String(technical) : null,
        physical_score: physical != null ? String(physical) : null,
        tactical_score: tactical != null ? String(tactical) : null,
        mental_score: mental != null ? String(mental) : null,
        attitude_score: attitude != null ? String(attitude) : null,
        comment,
        comment_visible_to_player: visibleToPlayer,
      });
      reset();
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue. Réessayez.");
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
      title="Évaluer un joueur"
      size="md"
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-text">Joueur</label>
          <PlayerSearch value={player} onChange={setPlayer} searchPlayers={searchActiveClubPlayers} />
        </div>
        <NumberField label="Note globale (/10)" value={overall} onChange={setOverall} min={0} max={10} step={0.5} />
        <div className="grid grid-cols-2 gap-3">
          <NumberField label="Technique" optional value={technical} onChange={setTechnical} min={0} max={10} step={0.5} />
          <NumberField label="Physique" optional value={physical} onChange={setPhysical} min={0} max={10} step={0.5} />
          <NumberField label="Tactique" optional value={tactical} onChange={setTactical} min={0} max={10} step={0.5} />
          <NumberField label="Mental" optional value={mental} onChange={setMental} min={0} max={10} step={0.5} />
          <NumberField label="Attitude" optional value={attitude} onChange={setAttitude} min={0} max={10} step={0.5} />
        </div>
        <TextArea label="Commentaire" optional value={comment} onChange={setComment} rows={3} />
        <Checkbox
          checked={visibleToPlayer}
          onChange={setVisibleToPlayer}
          label="Rendre ce commentaire visible par le joueur"
        />
        {error ? <p className="text-sm text-status-danger-fg">{error}</p> : null}
      </div>
    </Modal>
  );
}
