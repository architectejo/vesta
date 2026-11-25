import { useState } from "react";
import { appointAssistantCoach, revokeAssistantCoach, searchActiveClubPlayers } from "../../api/clubs";
import type { MembershipRole } from "../../api/clubs";
import { ApiError } from "../../api/client";
import { Avatar, Banner, Button, ConfirmDialog, EmptyState, Loader, Modal, PlayerSearch, useToast } from "../../design-system";
import type { PlayerSearchResult } from "../../design-system";

const GENERIC_ERROR = "Une erreur est survenue de notre côté. Réessayez dans un instant.";

/**
 * Section « Assistant du Coach » (CDC 2.2-2.4, 10.3 n°179). Visible de tous ;
 * nommer / retirer réservé au Coach strict (`canManage`). Un seul assistant :
 * nommer un nouveau remplace l'ancien (géré par l'API).
 */
export function AssistantCoachSection({
  assistant,
  assistantName,
  loading,
  canManage,
  onChanged,
}: {
  assistant: MembershipRole | undefined;
  assistantName: string | null;
  loading: boolean;
  canManage: boolean;
  onChanged: () => void;
}) {
  const { showToast } = useToast();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [selected, setSelected] = useState<PlayerSearchResult | null>(null);
  const [confirmAppoint, setConfirmAppoint] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function closeAll(): void {
    setPickerOpen(false);
    setConfirmAppoint(false);
    setConfirmRevoke(false);
    setSelected(null);
    setError(null);
  }

  async function run(action: () => Promise<unknown>, successMessage: string): Promise<void> {
    setSubmitting(true);
    setError(null);
    try {
      await action();
      showToast(successMessage);
      closeAll();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : GENERIC_ERROR);
    } finally {
      setSubmitting(false);
    }
  }

  const selectedName = selected ? `${selected.firstName} ${selected.lastName}` : "";

  return (
    <section className="rounded-lg bg-surface p-3 shadow-card sm:p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-text">Assistant du Coach</h2>
        {canManage ? (
          <Button variant="ghost" size="sm" disabled={loading} onClick={() => setPickerOpen(true)}>
            {assistant ? "Changer l'assistant" : "Nommer l'assistant"}
          </Button>
        ) : null}
      </div>
      <div className="mt-2">
        {loading ? (
          <Loader loading variant="list" count={1} />
        ) : assistant ? (
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2">
              <Avatar name={assistantName ?? "?"} size={32} />
              <div className="min-w-0">
                <p className="truncate text-sm text-text">{assistantName ?? "…"}</p>
                <p className="text-xs text-text-muted">
                  Assistant depuis le {new Date(assistant.appointed_at).toLocaleDateString("fr-FR")}
                </p>
              </div>
            </div>
            {canManage ? (
              <Button variant="ghost" size="sm" onClick={() => setConfirmRevoke(true)}>
                Retirer l'assistant
              </Button>
            ) : null}
          </div>
        ) : (
          <EmptyState message="Aucun assistant nommé" />
        )}
      </div>

      <Modal
        open={pickerOpen}
        onClose={closeAll}
        title={assistant ? "Changer l'assistant du Coach" : "Nommer l'assistant du Coach"}
        size="md"
        confirmLabel="Continuer"
        confirmDisabled={!selected}
        onConfirm={() => setConfirmAppoint(true)}
      >
        <div className="space-y-3">
          {assistant && assistantName ? (
            <p className="text-xs text-text-muted">{assistantName} sera remplacé.</p>
          ) : null}
          <PlayerSearch
            value={selected}
            onChange={setSelected}
            searchPlayers={searchActiveClubPlayers}
            ariaLabel="Choisir l'assistant"
            placeholder="Nom ou numéro du joueur"
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmAppoint && selected !== null}
        danger={false}
        title={`Nommer ${selectedName} assistant du Coach ?`}
        description={
          assistant
            ? "Il remplacera l'assistant actuel et aura les mêmes droits que le Coach (sauf nommer ou retirer l'assistant)."
            : "Il aura les mêmes droits que le Coach (sauf nommer ou retirer l'assistant)."
        }
        confirmLabel="Nommer"
        loading={submitting}
        error={error ?? undefined}
        onConfirm={() =>
          void run(
            () => appointAssistantCoach({ membership_id: Number(selected?.id) }),
            `${selectedName} est nommé assistant du Coach. Il a été prévenu.`,
          )
        }
        onCancel={() => {
          setConfirmAppoint(false);
          setError(null);
        }}
      />

      <ConfirmDialog
        open={confirmRevoke && assistant !== undefined}
        title={`Retirer ${assistantName ?? "l'assistant"} du poste d'assistant du Coach ?`}
        description="Il perdra les droits liés à ce poste. Il sera prévenu."
        confirmLabel="Retirer"
        loading={submitting}
        error={error ?? undefined}
        onConfirm={() =>
          void run(
            () => revokeAssistantCoach({ role_id: Number(assistant?.id) }),
            "L'assistant du Coach a été retiré.",
          )
        }
        onCancel={() => {
          setConfirmRevoke(false);
          setError(null);
        }}
      />
      {error && !confirmAppoint && !confirmRevoke ? <Banner variant="danger">{error}</Banner> : null}
    </section>
  );
}
