import { useState } from "react";
import { draftMinutes, type Assembly } from "../../../api/assemblies";
import { ApiError } from "../../../api/client";
import { Banner, Button, Modal, TextArea } from "../../../design-system";

function decisionsAsText(assembly: Assembly): string {
  return assembly.agenda_items
    .map((item) => {
      const decision = assembly.decisions.find((d) => d.agenda_item_id === item.id);
      if (!decision) return null;
      return `${item.title} : Pour ${decision.votes_for} · Contre ${decision.votes_against} · Abstention ${decision.votes_abstain}. Décision : ${decision.outcome}`;
    })
    .filter((line): line is string => Boolean(line))
    .join("\n");
}

/** Modale « Rédiger le procès-verbal » (assemblees-page-ag.md §4.4). */
export function MinutesEditModal({
  assembly,
  onClose,
  onSaved,
}: {
  assembly: Assembly;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [content, setContent] = useState(assembly.minutes?.content ?? "");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isDirty = content !== (assembly.minutes?.content ?? "");

  async function handleSubmit(): Promise<void> {
    setSubmitError(null);
    setSubmitting(true);
    try {
      await draftMinutes(assembly.id, content);
      onSaved();
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
      title="Rédiger le procès-verbal"
      size="lg"
      level={2}
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-3">
        {submitError ? <Banner variant="danger">{submitError}</Banner> : null}
        <TextArea
          label="Texte du procès-verbal"
          value={content}
          onChange={setContent}
          rows={12}
        />
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => setContent((current) => [current, decisionsAsText(assembly)].filter(Boolean).join("\n\n"))}
        >
          Insérer les décisions
        </Button>
      </div>
    </Modal>
  );
}
