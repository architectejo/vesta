import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { getMatchEquipment, recordMatchEquipmentReturn, type MatchEquipmentLine } from "../../api/logistics";
import { Button, Modal, NumberField, StatusBadge, TextArea } from "../../design-system";
import { formatDateFr } from "./format";
import { equipmentLineStatusKey } from "./materielLabels";

function apiErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.detail : "Une erreur est survenue de notre côté. Réessayez.";
}

export interface MatchEquipmentModalProps {
  open: boolean;
  matchId: number | null;
  opponent: string;
  eventDate: string;
  /** Coach et Intendant (fiche §5.2, point ouvert n° 4). */
  canRecordReturn: boolean;
  onClose: () => void;
  onReturned?: () => void;
}

/** « Équipements du match » (détail) — fiche `logistique.md` §4.6. Ouverte
 * depuis la feuille de match ou depuis la carte « Sortis pour un match ». */
export function MatchEquipmentModal({
  open,
  matchId,
  opponent,
  eventDate,
  canRecordReturn,
  onClose,
  onReturned,
}: MatchEquipmentModalProps) {
  const [returnOpen, setReturnOpen] = useState(false);
  const [quantities, setQuantities] = useState<Record<number, number | null>>({});
  const [observation, setObservation] = useState("");
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  const query = useQuery({
    queryKey: ["logistics", "match-equipment", matchId],
    queryFn: () => getMatchEquipment(matchId as number),
    enabled: open && matchId !== null,
  });
  const lines = query.data?.lines ?? [];
  const notSettled = lines.filter((line) => line.remaining_quantity > 0);

  useEffect(() => {
    if (!returnOpen) return;
    const initial: Record<number, number | null> = {};
    for (const line of notSettled) {
      initial[line.article_id] = line.remaining_quantity;
    }
    setQuantities(initial);
    setObservation("");
    setSubmitError(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [returnOpen]);

  async function handleSubmitReturn(): Promise<void> {
    if (matchId === null) return;
    const payload = notSettled
      .map((line) => ({ article_id: line.article_id, quantity_returned: quantities[line.article_id] ?? 0 }))
      .filter((entry) => entry.quantity_returned > 0);
    if (payload.length === 0) {
      setSubmitError("Saisissez au moins une quantité rendue.");
      return;
    }
    setSubmitting(true);
    setSubmitError(undefined);
    try {
      await recordMatchEquipmentReturn(matchId, payload, observation.trim() || undefined);
      setReturnOpen(false);
      void query.refetch();
      onReturned?.();
    } catch (error) {
      setSubmitError(apiErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={`Équipements · ${opponent}`}
        subtitle={eventDate ? formatDateFr(eventDate) : undefined}
        size="md"
        loading={query.isLoading}
        cancelLabel="Fermer"
        footer={
          <div className="flex w-full items-center justify-end gap-2">
            <Button variant="secondary" size="md" onClick={onClose}>
              Fermer
            </Button>
            {canRecordReturn && notSettled.length > 0 ? (
              <Button variant="primary" size="md" onClick={() => setReturnOpen(true)}>
                Enregistrer le retour
              </Button>
            ) : null}
          </div>
        }
      >
        {query.isError ? (
          <p role="alert" className="text-sm text-status-danger-fg">
            Impossible de charger ce détail. Réessayez.
          </p>
        ) : lines.length === 0 ? (
          <p className="text-sm text-text-muted">Aucun équipement enregistré pour ce match.</p>
        ) : (
          <ul className="divide-y divide-border">
            {lines.map((line) => (
              <li key={line.article_id} className="space-y-1 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm text-text">{line.article_name}</span>
                  <StatusBadge status={equipmentLineStatusKey(line.status)} />
                </div>
                <p className="text-xs text-text-muted">
                  {line.out_quantity} sortis · {line.returned_quantity} rendus
                  {line.status === "partially_returned" ? (
                    <span className="text-sm text-status-danger-fg"> · {line.remaining_quantity} non rendus</span>
                  ) : null}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Modal>

      <Modal
        open={returnOpen}
        onClose={() => setReturnOpen(false)}
        title="Enregistrer le retour"
        size="md"
        level={2}
        isSubmitting={submitting}
        confirmLabel="Enregistrer le retour"
        confirmLoadingLabel="Enregistrement…"
        onConfirm={() => void handleSubmitReturn()}
      >
        <div className="space-y-4">
          {notSettled.map((line: MatchEquipmentLine) => (
            <NumberField
              key={line.article_id}
              label={`${line.article_name} — sortis : ${line.out_quantity} · déjà rendus : ${line.returned_quantity}`}
              value={quantities[line.article_id] ?? 0}
              onChange={(value) =>
                setQuantities((current) => ({ ...current, [line.article_id]: value }))
              }
              min={0}
              max={line.remaining_quantity}
            />
          ))}
          <TextArea label="Observation" optional value={observation} onChange={setObservation} maxLength={500} />
          {submitError ? <p className="text-sm text-status-danger-fg">{submitError}</p> : null}
        </div>
      </Modal>
    </>
  );
}
