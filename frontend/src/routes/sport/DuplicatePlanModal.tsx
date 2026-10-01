import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { duplicateTacticalPlan, listMatches } from "../../api/sport";
import { Modal, TextField } from "../../design-system";

export interface DuplicatePlanModalProps {
  open: boolean;
  planId: number | null;
  planName: string;
  onClose: () => void;
  onDuplicated: (newPlanId: number, skippedCount: number) => void;
}

/** « Dupliquer le plan » (docs/ecrans/sport-plan-tactique.md §4.7). */
export function DuplicatePlanModal({ open, planId, planName, onClose, onDuplicated }: DuplicatePlanModalProps) {
  const [name, setName] = useState(`${planName} (copie)`);
  const [matchId, setMatchId] = useState<number | null>(null);
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  const matchesQuery = useQuery({
    queryKey: ["sport", "matches", "for-plan"],
    queryFn: () => listMatches({ limit: 50 }),
    enabled: open,
  });

  useEffect(() => {
    if (open) {
      setName(`${planName} (copie)`);
      setMatchId(null);
      setError(undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, planName]);

  async function handleSubmit(): Promise<void> {
    if (!planId) return;
    setSubmitting(true);
    setError(undefined);
    try {
      const result = await duplicateTacticalPlan(planId, { name: name.trim(), match_id: matchId });
      onDuplicated(result.id, result.skipped_count);
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
      title="Dupliquer le plan"
      size="sm"
      isSubmitting={submitting}
      confirmLabel="Dupliquer"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        <TextField label="Nom de la copie" value={name} onChange={setName} maxLength={120} />
        <label className="block text-sm font-medium text-text">
          Match rattaché (facultatif)
          <select
            className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-base"
            value={matchId ?? ""}
            onChange={(e) => setMatchId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Aucun match</option>
            {(matchesQuery.data?.results ?? []).map((m) => (
              <option key={m.id} value={m.id}>
                {m.opponent} · {m.event_date}
              </option>
            ))}
          </select>
        </label>
        <p className="text-xs text-text-muted">
          La copie est un brouillon. Les joueurs qui ne peuvent pas jouer aujourd'hui ne sont pas recopiés.
        </p>
        {error ? <p className="text-sm text-status-danger-fg">{error}</p> : null}
      </div>
    </Modal>
  );
}
