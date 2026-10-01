import { useState } from "react";
import { recordDecision, type Assembly, type Decision } from "../../../api/assemblies";
import { ApiError } from "../../../api/client";
import { Banner, Modal, NumberField, TextArea } from "../../../design-system";

/** Modale « Saisir le vote » (assemblees-page-ag.md §4.3). Jamais bloquant
 * sur le quorum ni sur le total des votes (avertissement seulement). */
export function DecisionModal({
  assembly,
  agendaItemId,
  existing,
  presentCount,
  onClose,
  onSaved,
}: {
  assembly: Assembly;
  agendaItemId: number;
  existing: Decision | undefined;
  presentCount: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const agendaItem = assembly.agenda_items.find((i) => i.id === agendaItemId);
  const [votesFor, setVotesFor] = useState<number | null>(existing?.votes_for ?? 0);
  const [votesAgainst, setVotesAgainst] = useState<number | null>(existing?.votes_against ?? 0);
  const [votesAbstain, setVotesAbstain] = useState<number | null>(existing?.votes_abstain ?? 0);
  const [outcome, setOutcome] = useState(existing?.outcome ?? "");
  const [outcomeError, setOutcomeError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const total = (votesFor ?? 0) + (votesAgainst ?? 0) + (votesAbstain ?? 0);
  const exceedsPresent = total > presentCount;

  const isDirty =
    votesFor !== (existing?.votes_for ?? 0) ||
    votesAgainst !== (existing?.votes_against ?? 0) ||
    votesAbstain !== (existing?.votes_abstain ?? 0) ||
    outcome !== (existing?.outcome ?? "");

  async function handleSubmit(): Promise<void> {
    setOutcomeError(undefined);
    setSubmitError(null);
    if (!outcome.trim()) {
      setOutcomeError("Ce champ est obligatoire.");
      return;
    }
    setSubmitting(true);
    try {
      await recordDecision(assembly.id, agendaItemId, {
        votes_for: votesFor ?? 0,
        votes_against: votesAgainst ?? 0,
        votes_abstain: votesAbstain ?? 0,
        outcome: outcome.trim(),
      });
      onSaved();
    } catch (err) {
      if (err instanceof ApiError && err.fieldError("votes_abstain")) {
        setSubmitError(err.fieldError("votes_abstain") ?? null);
      } else {
        setSubmitError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Saisir le vote — ${agendaItem?.title ?? ""}`}
      size="md"
      level={2}
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-4">
        {submitError ? <Banner variant="danger">{submitError}</Banner> : null}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <NumberField label="Pour" value={votesFor} onChange={setVotesFor} min={0} />
          <NumberField label="Contre" value={votesAgainst} onChange={setVotesAgainst} min={0} />
          <NumberField label="Abstention" value={votesAbstain} onChange={setVotesAbstain} min={0} />
        </div>
        <p className={`text-[13px] ${exceedsPresent ? "text-status-warning-fg" : "text-text-muted"}`}>
          {exceedsPresent
            ? `Le total des votes (${total}) dépasse le nombre de présents (${presentCount}). Vérifiez la saisie.`
            : `Total : ${total} votes · ${presentCount} présents`}
        </p>
        <TextArea
          label="Décision retenue"
          value={outcome}
          onChange={setOutcome}
          error={outcomeError}
          rows={3}
        />
      </div>
    </Modal>
  );
}
