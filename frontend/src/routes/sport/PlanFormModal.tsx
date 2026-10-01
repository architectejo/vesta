import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { listMatches, type Formation, type SquadSize, type TacticalPlanInput } from "../../api/sport";
import { FORMATION_LABELS, Modal, SegmentedControl, TextField, formationsForSquadSize } from "../../design-system";

export interface PlanFormModalProps {
  open: boolean;
  mode: "create" | "settings";
  initial?: { name: string; formation: Formation; squadSize: SquadSize; matchId: number | null };
  onClose: () => void;
  onSubmit: (input: TacticalPlanInput) => Promise<void>;
}

/**
 * « Nouveau plan » (§4.2) et « Paramètres du plan » (§4.3) : mêmes champs,
 * repris ici dans un seul composant. Le choix de formation est **limité
 * aux combinaisons acceptées par le service** (`TacticalPlan.clean`,
 * backend/apps/sport/models.py) : à effectif réduit (7/8), seule
 * « Personnalisée » est proposée — voir `design-system/tactics/
 * formations.ts` et le point ouvert signalé au compte rendu (503 non
 * traduite sur une combinaison invalide, contournée ici en amont).
 */
export function PlanFormModal({ open, mode, initial, onClose, onSubmit }: PlanFormModalProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [squadSize, setSquadSize] = useState<SquadSize>(initial?.squadSize ?? 11);
  const [formation, setFormation] = useState<Formation>(initial?.formation ?? "4-4-2");
  const [matchId, setMatchId] = useState<number | null>(initial?.matchId ?? null);
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  const matchesQuery = useQuery({
    queryKey: ["sport", "matches", "for-plan"],
    queryFn: () => listMatches({ limit: 50 }),
    enabled: open,
  });
  const upcoming = (matchesQuery.data?.results ?? []).filter(
    (m) => m.event_date >= new Date().toISOString().slice(0, 10),
  );

  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? "");
    setSquadSize(initial?.squadSize ?? 11);
    setFormation(initial?.formation ?? "4-4-2");
    setMatchId(initial?.matchId ?? null);
    setError(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const availableFormations = formationsForSquadSize(squadSize);

  function handleSquadSizeChange(next: SquadSize): void {
    setSquadSize(next);
    const options = formationsForSquadSize(next);
    if (!options.includes(formation)) setFormation(options[0] ?? "custom");
  }

  async function handleSubmit(): Promise<void> {
    if (!name.trim()) {
      setError("Ce champ est obligatoire.");
      return;
    }
    setSubmitting(true);
    setError(undefined);
    try {
      await onSubmit({ name: name.trim(), formation, squad_size: squadSize, match_id: matchId });
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
      title={mode === "create" ? "Nouveau plan" : "Paramètres du plan"}
      size="md"
      isSubmitting={submitting}
      confirmLabel={mode === "create" ? "Créer le plan" : "Enregistrer"}
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <TextField label="Nom du plan" value={name} onChange={setName} maxLength={120} error={error} />
        <SegmentedControl
          label="Effectif"
          value={String(squadSize) as "7" | "8" | "11"}
          onChange={(v) => handleSquadSizeChange(Number(v) as SquadSize)}
          options={[
            { value: "11", label: "11" },
            { value: "8", label: "8" },
            { value: "7", label: "7" },
          ]}
        />
        <label className="block text-sm font-medium text-text">
          Formation
          <select
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base disabled:opacity-60"
            value={formation}
            disabled={availableFormations.length <= 1}
            onChange={(e) => setFormation(e.target.value as Formation)}
          >
            {availableFormations.map((f) => (
              <option key={f} value={f}>
                {FORMATION_LABELS[f]}
              </option>
            ))}
          </select>
        </label>
        {squadSize !== 11 ? (
          <p className="text-xs text-text-muted">
            À effectif réduit, seule la formation « Personnalisée » est disponible pour l'instant.
          </p>
        ) : (
          <p className="text-xs text-text-muted">
            Vous pourrez déplacer les emplacements ensuite : la formation deviendra « Personnalisée ».
          </p>
        )}
        <label className="block text-sm font-medium text-text">
          Match rattaché (facultatif)
          <select
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
            value={matchId ?? ""}
            onChange={(e) => setMatchId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Aucun match</option>
            {upcoming.map((m) => (
              <option key={m.id} value={m.id}>
                {m.opponent} · {m.event_date}
              </option>
            ))}
          </select>
        </label>
      </div>
    </Modal>
  );
}
