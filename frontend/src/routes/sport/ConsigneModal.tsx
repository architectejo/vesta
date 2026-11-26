import { useState } from "react";
import { ApiError } from "../../api/client";
import { addAnnotation, removeAnnotation, type Annotation, type Placement } from "../../api/sport";
import { ConfirmDialog, Modal, PlayerSearch, SegmentedControl, TextArea, type PlayerSearchResult } from "../../design-system";

type ConsigneTarget = "everyone" | "line" | "player";

export interface ConsigneModalProps {
  open: boolean;
  planId: number;
  placements: Placement[];
  existing?: Annotation | null;
  initialPoint?: { x: number; y: number } | null;
  onClose: () => void;
  onSaved: () => void;
  onDeleted?: () => void;
}

/** « Consigne » (docs/ecrans/sport-plan-tactique.md §4.6). */
export function ConsigneModal({ open, planId, placements, existing, initialPoint, onClose, onSaved, onDeleted }: ConsigneModalProps) {
  const [target, setTarget] = useState<ConsigneTarget>(
    existing?.target_membership_id ? "player" : existing?.target_line ? "line" : "everyone",
  );
  const [line, setLine] = useState<"defense" | "midfield" | "attack">((existing?.target_line as "defense" | "midfield" | "attack") || "defense");
  const [player, setPlayer] = useState<PlayerSearchResult | null>(
    existing?.target_membership_id
      ? (() => {
          const p = placements.find((pl) => pl.membership_id === existing.target_membership_id);
          return p?.player ? { id: p.player.membership_id, firstName: p.player.name, lastName: "" } : null;
        })()
      : null,
  );
  const [text, setText] = useState(existing?.text ?? "");
  const [error, setError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const placedPlayers = placements.filter((p) => p.player);

  async function searchPlaced(query: string): Promise<PlayerSearchResult[]> {
    const q = query.trim().toLowerCase();
    return placedPlayers
      .filter((p) => !q || (p.player?.name ?? "").toLowerCase().includes(q))
      .map((p) => ({ id: p.player!.membership_id, firstName: p.player!.name, lastName: "" }));
  }

  async function handleSubmit(): Promise<void> {
    if (target === "line" && !line) {
      setError("Choisissez une ligne.");
      return;
    }
    if (target === "player" && !player) {
      setError("Choisissez un joueur.");
      return;
    }
    if (!text.trim()) {
      setError("Ce champ est obligatoire.");
      return;
    }
    setSubmitting(true);
    setError(undefined);
    try {
      // La modification d'une consigne existante n'a pas de route PATCH
      // dédiée (backend/apps/sport/urls.py : seuls create/delete sont
      // exposés) — on recrée l'annotation et on retire l'ancienne.
      await addAnnotation(planId, {
        annotation_type: "note",
        text: text.trim(),
        target_membership_id: target === "player" ? Number(player!.id) : null,
        target_line: target === "line" ? line : "",
        path_data: initialPoint ? JSON.stringify([initialPoint]) : "",
      });
      if (existing) await removeAnnotation(existing.id);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(): Promise<void> {
    if (!existing) return;
    setSubmitting(true);
    try {
      await removeAnnotation(existing.id);
      onDeleted?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Suppression impossible.");
    } finally {
      setSubmitting(false);
      setConfirmDelete(false);
    }
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="Consigne"
        size="sm"
        isSubmitting={submitting}
        confirmLabel="Enregistrer"
        onConfirm={() => void handleSubmit()}
        footer={
          <div className="flex w-full items-center justify-between gap-2">
            {existing ? (
              <button type="button" onClick={() => setConfirmDelete(true)} className="inline-flex min-h-control-sm items-center text-sm text-status-danger-fg hover:underline">
                Supprimer la consigne
              </button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <button type="button" onClick={onClose} className="h-control-md rounded-sm border border-border-strong px-4 text-sm">
                Annuler
              </button>
              <button
                type="button"
                onClick={() => void handleSubmit()}
                className="h-control-md rounded-sm bg-primary px-4 text-sm text-on-primary"
              >
                Enregistrer
              </button>
            </div>
          </div>
        }
      >
        <div className="space-y-4">
          <SegmentedControl
            label="Pour"
            value={target}
            onChange={setTarget}
            options={[
              { value: "everyone", label: "Tout le monde" },
              { value: "line", label: "Une ligne" },
              { value: "player", label: "Un joueur" },
            ]}
          />
          {target === "line" ? (
            <SegmentedControl
              label="Ligne"
              value={line}
              onChange={setLine}
              options={[
                { value: "defense", label: "Défense" },
                { value: "midfield", label: "Milieu" },
                { value: "attack", label: "Attaque" },
              ]}
            />
          ) : null}
          {target === "player" ? (
            <div>
              <label className="mb-1 block text-sm font-medium text-text">Joueur</label>
              <PlayerSearch value={player} onChange={setPlayer} searchPlayers={searchPlaced} />
            </div>
          ) : null}
          <TextArea label="Texte" value={text} onChange={setText} maxLength={300} showCount rows={3} />
          {error ? <p className="text-sm text-status-danger-fg">{error}</p> : null}
        </div>
      </Modal>
      <ConfirmDialog
        open={confirmDelete}
        title="Supprimer cette consigne ?"
        confirmLabel="Supprimer"
        loading={submitting}
        onConfirm={() => void handleDelete()}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  );
}
