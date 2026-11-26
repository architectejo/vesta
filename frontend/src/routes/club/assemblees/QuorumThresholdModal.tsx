import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getQuorumThreshold, updateQuorumThreshold } from "../../../api/assemblies";
import { ApiError } from "../../../api/client";
import { Banner, Modal, TextField, useToast } from "../../../design-system";

const DEFAULT_PERCENTAGE = 50;

/** Modale « Seuil de quorum » (assemblees-page-ag.md §4.5 ; 10.2 n° 18). */
export function QuorumThresholdModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const query = useQuery({ queryKey: ["assemblies", "quorum-threshold"], queryFn: getQuorumThreshold });

  const [value, setValue] = useState<string>("");
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (query.data && !touched) setValue(query.data.percentage);
  }, [query.data, touched]);

  const currentPercentage = query.data ? Number(query.data.percentage) : null;
  const isDirty = touched && value !== (query.data?.percentage ?? "");

  async function handleSubmit(): Promise<void> {
    setError(undefined);
    setSubmitError(null);
    const trimmed = value.trim();
    if (trimmed === "") {
      setError("Ce champ est obligatoire.");
      return;
    }
    const numeric = Number(trimmed);
    if (!Number.isInteger(numeric) || numeric < 1 || numeric > 100) {
      setError("Saisissez une valeur entre 1 et 100.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await updateQuorumThreshold(numeric);
      await queryClient.invalidateQueries({ queryKey: ["assemblies"] });
      showToast(`Seuil de quorum enregistré : ${result.percentage} %.`);
      onClose();
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Seuil de quorum"
      size="sm"
      level={2}
      isDirty={isDirty}
      isSubmitting={submitting}
      loading={query.isLoading}
      confirmLabel="Enregistrer"
      onConfirm={() => void handleSubmit()}
      confirmLoadingLabel="Enregistrement…"
    >
      <div className="space-y-3">
        {submitError ? <Banner variant="danger">{submitError}</Banner> : null}
        <TextField
          label="Seuil de quorum (%)"
          value={value}
          onChange={(v) => {
            setValue(v.replace(/[^0-9]/g, ""));
            setTouched(true);
          }}
          rightSlot={<span className="text-sm text-text-muted">%</span>}
          error={error}
          help="Pourcentage des joueurs actifs à la date de l'AG qui doivent être présents. Valeur par défaut : 50 %."
          inputMode="numeric"
        />
        {currentPercentage !== null && currentPercentage !== DEFAULT_PERCENTAGE ? (
          <button
            type="button"
            className="inline-flex min-h-control-sm items-center text-xs font-medium text-primary-text hover:underline"
            onClick={() => {
              setValue(String(DEFAULT_PERCENTAGE));
              setTouched(true);
            }}
          >
            Revenir à 50 %
          </button>
        ) : null}
      </div>
    </Modal>
  );
}
