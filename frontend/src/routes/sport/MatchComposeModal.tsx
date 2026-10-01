import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { listClubPlayers, type ClubPlayerListItem } from "../../api/clubs";
import { addToComposition, type CompositionEntry } from "../../api/sport";
import { Avatar, Modal, NumberField, SegmentedControl } from "../../design-system";

const POSITION_OPTIONS = [
  { value: "goalkeeper", label: "Gardien" },
  { value: "defender", label: "Défenseur" },
  { value: "midfielder", label: "Milieu" },
  { value: "forward", label: "Attaquant" },
] as const;

interface DraftRow {
  role: "starter" | "substitute";
  position: string;
  jerseyNumber: number | null;
}

export interface MatchComposeModalProps {
  open: boolean;
  matchId: number;
  existing: CompositionEntry[];
  onClose: () => void;
  onSaved: () => void;
}

/**
 * « Composer l'équipe » (docs/ecrans/sport-feuille-de-match.md §4.1).
 *
 * **Écart signalé au compte rendu** : le CDC prévoit un pré-grisage des
 * joueurs non sélectionnables (dette, suspension, inaptitude, attente
 * d'adhésion) directement dans cette liste, avec rafraîchissement toutes
 * les 15 s (§4.1 bis). Aucune route de l'API livrée (`apps.clubs`/
 * `apps.sport`) ne renvoie l'éligibilité de tout l'effectif en une fois —
 * seul le service `add_to_composition` la connaît, joueur par joueur, au
 * moment de la tentative. Le contrôle réel (CLAUDE.md règle n° 5) reste
 * donc entièrement fait par ce service : un joueur non sélectionnable
 * n'est jamais réellement composé, mais l'interface ne peut pas le griser
 * par avance. L'erreur de l'API s'affiche alors sur sa ligne, telle
 * quelle. Point à remonter pour une prochaine itération (endpoint
 * d'éligibilité groupée).
 */
export function MatchComposeModal({ open, matchId, existing, onClose, onSaved }: MatchComposeModalProps) {
  const [search, setSearch] = useState("");
  const [drafts, setDrafts] = useState<Record<number, DraftRow>>({});
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const rosterQuery = useQuery({
    queryKey: ["clubs", "players", "active"],
    queryFn: () => listClubPlayers({ status: "active" }),
    enabled: open,
  });

  const alreadyComposed = useMemo(() => new Set(existing.map((e) => e.membership_id)), [existing]);

  const filtered = (rosterQuery.data ?? []).filter((player) => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
    return (
      `${player.first_name} ${player.last_name}`.toLowerCase().includes(q) ||
      String(player.jersey_number ?? "").includes(q)
    );
  });

  function toggle(player: ClubPlayerListItem): void {
    setDrafts((current) => {
      const next = { ...current };
      if (next[player.membership_id]) {
        delete next[player.membership_id];
      } else {
        next[player.membership_id] = {
          role: "starter",
          position: player.position,
          jerseyNumber: player.jersey_number,
        };
      }
      return next;
    });
  }

  function updateDraft(membershipId: number, patch: Partial<DraftRow>): void {
    setDrafts((current) => ({ ...current, [membershipId]: { ...current[membershipId]!, ...patch } }));
  }

  async function handleSubmit(): Promise<void> {
    setSubmitting(true);
    const errors: Record<number, string> = {};
    for (const [idStr, draft] of Object.entries(drafts)) {
      const membershipId = Number(idStr);
      if (alreadyComposed.has(membershipId)) continue;
      if (draft.jerseyNumber == null) {
        errors[membershipId] = "Indiquez un numéro du jour.";
        continue;
      }
      try {
        await addToComposition(matchId, {
          membership_id: membershipId,
          role: draft.role,
          position: draft.position,
          jersey_number: draft.jerseyNumber,
        });
      } catch (error) {
        errors[membershipId] = error instanceof ApiError ? error.detail : "Enregistrement impossible.";
      }
    }
    setRowErrors(errors);
    setSubmitting(false);
    if (Object.keys(errors).length === 0) {
      setDrafts({});
      onSaved();
    }
  }

  const selectedCount = Object.keys(drafts).length;
  const starterCount = Object.values(drafts).filter((d) => d.role === "starter").length;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Composer l'équipe"
      size="lg"
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      confirmDisabled={selectedCount === 0}
      onConfirm={() => void handleSubmit()}
    >
      <div className="space-y-3">
        <input
          type="text"
          placeholder="Nom ou numéro"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text placeholder:text-text-muted"
        />
        <p className="text-xs text-text-muted">
          {starterCount} titulaires · {selectedCount - starterCount} remplaçants
        </p>

        {rosterQuery.isLoading ? (
          <p className="text-sm text-text-muted">Chargement…</p>
        ) : (
          <ul className="divide-y divide-border">
            {filtered.map((player) => {
              const composed = alreadyComposed.has(player.membership_id);
              const draft = drafts[player.membership_id];
              const error = rowErrors[player.membership_id];
              return (
                <li key={player.membership_id} className="py-2">
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      className="h-4 w-4 shrink-0"
                      checked={Boolean(draft) || composed}
                      disabled={composed}
                      onChange={() => toggle(player)}
                      aria-label={`Sélectionner ${player.first_name} ${player.last_name}`}
                    />
                    <Avatar name={`${player.first_name} ${player.last_name}`} photoUrl={player.photo} size={40} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-text">
                        {player.first_name} {player.last_name}
                        {composed ? " (déjà composé)" : ""}
                      </p>
                      <p className="truncate text-xs text-text-muted">{player.position_label}</p>
                    </div>
                  </div>
                  {draft && !composed ? (
                    <div className="mt-2 flex flex-wrap items-end gap-3 pl-7">
                      <SegmentedControl
                        label="Rôle"
                        value={draft.role}
                        onChange={(v) => updateDraft(player.membership_id, { role: v })}
                        options={[
                          { value: "starter", label: "Titulaire" },
                          { value: "substitute", label: "Remplaçant" },
                        ]}
                      />
                      <label className="block text-sm font-medium text-text">
                        Poste du jour
                        <select
                          className="mt-1 h-control-md rounded-sm border border-border-strong bg-surface px-2 text-base"
                          value={draft.position}
                          onChange={(e) => updateDraft(player.membership_id, { position: e.target.value })}
                        >
                          {POSITION_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <NumberField
                        label="N° du jour"
                        value={draft.jerseyNumber}
                        onChange={(v) => updateDraft(player.membership_id, { jerseyNumber: v })}
                        min={1}
                        max={99}
                      />
                    </div>
                  ) : null}
                  {error ? <p className="mt-1 pl-7 text-xs text-status-danger-fg">{error}</p> : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Modal>
  );
}
