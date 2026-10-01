import { useState } from "react";
import { appointRole, revokeRole, searchActiveClubPlayers } from "../../api/clubs";
import type { MembershipRole } from "../../api/clubs";
import { ApiError } from "../../api/client";
import { Banner, Modal, PlayerMultiSearch, useToast } from "../../design-system";
import type { PlayerSearchResult } from "../../design-system";

/**
 * Modale « Joueurs autorisés à ajouter des joueurs » (club-comite-bureau.md
 * §4.4), Président uniquement. `PlayerMultiSearch` bornée aux joueurs
 * inscrits (`status: "active"`, même règle que le parrain en §4.5).
 */
export function RecruitersModal({
  recruiters,
  onClose,
  onChanged,
}: {
  /** Titulaires actuels du rôle `player_recruiter`, avec leur fiche minimale. */
  recruiters: Array<{ role: MembershipRole; player: PlayerSearchResult }>;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { showToast } = useToast();
  const initial = recruiters.map((r) => r.player);
  const [selected, setSelected] = useState<PlayerSearchResult[]>(initial);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const initialIds = new Set(recruiters.map((r) => Number(r.player.id)));
  const selectedIds = new Set(selected.map((p) => Number(p.id)));
  const isDirty =
    initialIds.size !== selectedIds.size || [...initialIds].some((id) => !selectedIds.has(id));

  async function handleSave(): Promise<void> {
    setSubmitting(true);
    setError(null);
    try {
      const toAdd = selected.filter((p) => !initialIds.has(Number(p.id)));
      const toRemove = recruiters.filter((r) => !selectedIds.has(Number(r.player.id)));
      for (const player of toAdd) {
        await appointRole({ membership_id: Number(player.id), role: "player_recruiter" });
      }
      for (const r of toRemove) {
        await revokeRole({ role_id: r.role.id });
      }
      showToast("Autorisations mises à jour.");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Une erreur est survenue de notre côté. Réessayez dans un instant.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Joueurs autorisés à ajouter des joueurs"
      size="md"
      isDirty={isDirty}
      isSubmitting={submitting}
      confirmLabel="Enregistrer"
      confirmLoadingLabel="Enregistrement…"
      onConfirm={() => void handleSave()}
    >
      <div className="space-y-4">
        {error ? <Banner variant="danger">{error}</Banner> : null}
        <PlayerMultiSearch
          values={selected}
          onChange={setSelected}
          searchPlayers={searchActiveClubPlayers}
          ariaLabel="Ajouter un joueur autorisé à ajouter des joueurs"
          placeholder="Nom ou numéro du joueur"
        />
      </div>
    </Modal>
  );
}
