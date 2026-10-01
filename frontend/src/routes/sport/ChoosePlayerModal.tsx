import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listClubPlayers } from "../../api/clubs";
import type { Placement } from "../../api/sport";
import { Avatar, Modal } from "../../design-system";
import type { FormationSlot } from "../../design-system/tactics/formations";

export interface ChoosePlayerModalProps {
  open: boolean;
  slot: FormationSlot | null;
  placements: Placement[];
  onClose: () => void;
  onChoose: (membershipId: number) => void;
}

const KIND_LABEL: Record<string, string> = {
  goalkeeper: "Gardien",
  defender: "Défenseur",
  midfielder: "Milieu",
  forward: "Attaquant",
};

/** « Choisir un joueur » (docs/ecrans/sport-plan-tactique.md §4.4). */
export function ChoosePlayerModal({ open, slot, placements, onClose, onChoose }: ChoosePlayerModalProps) {
  const [search, setSearch] = useState("");
  const rosterQuery = useQuery({
    queryKey: ["clubs", "players", "active"],
    queryFn: () => listClubPlayers({ status: "active" }),
    enabled: open,
  });

  const placedByMember = new Map(placements.filter((p) => p.membership_id != null).map((p) => [p.membership_id as number, p]));

  const results = (rosterQuery.data ?? [])
    .filter((p) => {
      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return `${p.first_name} ${p.last_name}`.toLowerCase().includes(q) || String(p.jersey_number ?? "").includes(q);
    })
    .sort((a, b) => {
      const aSame = slot && a.position === slot.abbrev[0]?.toLowerCase() ? 0 : 1;
      const bSame = slot && b.position === slot.abbrev[0]?.toLowerCase() ? 0 : 1;
      return aSame - bSame;
    });

  return (
    <Modal open={open} onClose={onClose} title="Choisir un joueur" subtitle={slot ? `Emplacement : ${slot.abbrev}` : undefined} size="sm" hideFooter>
      <div className="space-y-3">
        <input
          type="text"
          placeholder="Nom ou numéro"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-text placeholder:text-text-muted"
        />
        <ul className="max-h-96 divide-y divide-border overflow-y-auto">
          {results.map((player) => {
            const already = placedByMember.get(player.membership_id);
            return (
              <li key={player.membership_id}>
                <button
                  type="button"
                  onClick={() => onChoose(player.membership_id)}
                  className="flex w-full items-center gap-3 py-2 text-left hover:bg-surface-muted"
                >
                  <Avatar name={`${player.first_name} ${player.last_name}`} photoUrl={player.photo} size={40} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-text">
                      {player.first_name} {player.last_name}
                    </p>
                    <p className="truncate text-xs text-text-muted">
                      {already ? `Déjà placé (${already.position_override || player.position_label})` : player.position_label}
                    </p>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </Modal>
  );
}

export { KIND_LABEL };
