import { useState } from "react";
import { ApiError } from "../../api/client";
import { updatePlacement, type Placement } from "../../api/sport";
import { Modal, NumberField } from "../../design-system";

const POSITION_OPTIONS = [
  { value: "goalkeeper", label: "Gardien" },
  { value: "defender", label: "Défenseur" },
  { value: "midfielder", label: "Milieu" },
  { value: "forward", label: "Attaquant" },
];

export interface NumberPositionModalProps {
  open: boolean;
  placement: Placement | null;
  onClose: () => void;
  onUpdated: (warning: string | null) => void;
}

/** « Modifier le numéro et le poste » (docs/ecrans/sport-plan-tactique.md §4.5). */
export function NumberPositionModal({ open, placement, onClose, onUpdated }: NumberPositionModalProps) {
  const [number, setNumber] = useState<number | null>(placement?.jersey_number_override ?? placement?.player?.jersey_number ?? null);
  const [position, setPosition] = useState(placement?.position_override || placement?.player?.position || "goalkeeper");
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(): Promise<void> {
    if (!placement) return;
    setSubmitting(true);
    setError(undefined);
    try {
      const result = await updatePlacement(placement.id, { jersey_number: number, position });
      onUpdated(result.warning ?? null);
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
      title="Modifier le numéro et le poste"
      subtitle={placement?.player?.name}
      size="sm"
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <NumberField label="Numéro de maillot" value={number} onChange={setNumber} min={1} max={99} />
        <label className="block text-sm font-medium text-text">
          Poste
          <select
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
            value={position}
            onChange={(e) => setPosition(e.target.value)}
          >
            {POSITION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <p className="text-xs text-text-muted">La fiche du joueur sera mise à jour.</p>
        {error ? <p className="text-sm text-status-danger-fg">{error}</p> : null}
      </div>
    </Modal>
  );
}
