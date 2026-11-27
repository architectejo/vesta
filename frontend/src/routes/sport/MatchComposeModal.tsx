import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { listClubPlayers, type ClubPlayerListItem } from "../../api/clubs";
import { addToComposition, type CompositionEntry } from "../../api/sport";
import { Avatar, Modal, NumberField, SegmentedControl } from "../../design-system";
import { useEligibility } from "./useEligibility";

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
 * Pré-grisage (§4.1 bis, série 6) : la liste de l'effectif porte
 * `is_unavailable` ; un joueur en dette, suspendu, inapte ou en attente
 * d'adhésion a sa case désactivée et n'est jamais envoyé. Le motif lisible
 * (« En dette : 10.00 USD. »…) est lu tel quel dans `GET /sport/eligibility/`
 * (`useEligibility`) et affiché sous le nom ; il n'est jamais recalculé ici.
 * Si cet appel échoue (403, réseau), la ligne garde le texte générique.
 * **Écart restant** : pas de rafraîchissement périodique de 15 s ni de
 * bandeau « n'est plus sélectionnable » pendant la saisie ; le contrôle réel (CLAUDE.md règle n° 5) reste fait par le service
 * `add_to_composition`, dont l'erreur s'affiche sur la ligne.
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

  const eligibility = useEligibility(open);

  const alreadyComposed = useMemo(() => new Set(existing.map((e) => e.membership_id)), [existing]);
  // Non sélectionnable si l'effectif OU l'éligibilité groupée le disent :
  // deux réponses de l'API, aucune règle évaluée ici.
  const blockedIds = useMemo(
    () =>
      new Set(
        (rosterQuery.data ?? [])
          .filter((p) => p.is_unavailable || eligibility.get(p.membership_id)?.eligible === false)
          .map((p) => p.membership_id),
      ),
    [rosterQuery.data, eligibility],
  );

  // Sélectionnables d'abord, non sélectionnables ensuite (§4.1).
  const sorted = [...(rosterQuery.data ?? [])].sort(
    (a, b) => Number(blockedIds.has(a.membership_id)) - Number(blockedIds.has(b.membership_id)),
  );
  const filtered = sorted.filter((player) => {
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
      if (blockedIds.has(membershipId)) continue;
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
              // §4.1 bis : un joueur en dette, suspendu, inapte ou en attente
              // n'est jamais cochable (CLAUDE.md règle 5). Le motif est le texte
              // de l'API ; le service de composition reste le contrôle réel.
              const blocked = blockedIds.has(player.membership_id) && !composed;
              const eligibilityItem = eligibility.get(player.membership_id);
              const reason = eligibilityItem && !eligibilityItem.eligible ? eligibilityItem.reason.trim() : "";
              const draft = drafts[player.membership_id];
              const error = rowErrors[player.membership_id];
              return (
                <li key={player.membership_id} className="py-2">
                  <div className={["flex items-center gap-3", blocked ? "opacity-60" : ""].join(" ")}>
                    {/* Zone tactile de 44 px autour de la case (§4.1, B7). */}
                    <label className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center">
                      <input
                        type="checkbox"
                        className="h-5 w-5 shrink-0"
                        checked={(Boolean(draft) || composed) && !blocked}
                        disabled={composed || blocked}
                        aria-disabled={composed || blocked}
                        onChange={() => toggle(player)}
                        aria-label={`Sélectionner ${player.first_name} ${player.last_name}`}
                      />
                    </label>
                    <Avatar name={`${player.first_name} ${player.last_name}`} photoUrl={player.photo} size={40} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-text">
                        {player.first_name} {player.last_name}
                        {composed ? " (déjà composé)" : ""}
                      </p>
                      <p className="truncate text-xs text-text-muted">{player.position_label}</p>
                      {blocked ? (
                        // 14 px : information critique (§4.1 bis, 10.2 n° 31).
                        <p className="text-sm text-status-danger-fg">
                          {reason || "Non sélectionnable (dette, suspension, inaptitude ou adhésion en attente)"}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  {draft && !composed && !blocked ? (
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
