import { useState } from "react";
import type { MembershipBrief } from "../../api/sport";
import { FilterChips, PitchPin } from "../../design-system";
import { shortLabel } from "./pinLayout";
import {
  ALL_POSITIONS_LABEL,
  POSITION_FILTER_OPTIONS,
  compareByPositionThenName,
  groupByPosition,
  matchesPositionFilter,
  type PositionFilter,
} from "./positionGroups";

/**
 * « À placer à la main » de l'onglet « Équipes A/B » (sport-seance.md §3.2) :
 * présents non répartis automatiquement, à glisser vers l'équipe A ou B.
 *
 * Demande du client (remarques.md) : la liste est subdivisée par poste pour
 * faciliter la répartition. Mêmes puces, même tri et mêmes intertitres que
 * « Composer l'équipe » (sport-feuille-de-match.md §4.1) : purement
 * d'affichage, le poste est celui renvoyé par l'API.
 */
export function UnplacedPlayersPanel({
  players,
  draggable,
  onTapPlayer,
}: {
  players: MembershipBrief[];
  draggable: boolean;
  onTapPlayer: (membershipId: number, name: string) => void;
}) {
  const [positionFilter, setPositionFilter] = useState<PositionFilter>("");
  const visible = players
    .filter((p) => matchesPositionFilter(p.position, positionFilter))
    .sort(compareByPositionThenName);
  // Sous « Tous » : un intertitre par poste ; sous une puce, grille simple.
  const sections =
    positionFilter === ""
      ? groupByPosition(visible, (p) => p.position).map((g) => ({ key: g.key, label: g.label as string | null, items: g.items }))
      : [{ key: positionFilter, label: null, items: visible }];
  const positionLabel = POSITION_FILTER_OPTIONS.find((o) => o.value === positionFilter)?.label;

  return (
    <div className="space-y-2">
      {players.length > 1 ? (
        <FilterChips
          label="Filtrer les joueurs à placer par poste"
          value={positionFilter}
          onChange={setPositionFilter}
          options={POSITION_FILTER_OPTIONS}
          allLabel={ALL_POSITIONS_LABEL}
        />
      ) : null}
      {visible.length === 0 ? (
        <p className="text-sm text-text-muted">Aucun joueur à placer dans « {positionLabel} ».</p>
      ) : (
        sections.map((section) => (
          <section key={section.key} aria-label={section.label ?? undefined}>
            {section.label ? (
              <h4 className="mb-1 text-[13px] font-semibold text-text-muted">
                {section.label} ({section.items.length})
              </h4>
            ) : null}
            <div className="grid grid-cols-4 gap-2">
              {section.items.map((player) => (
                <PitchPin
                  key={player.membership_id}
                  vertical
                  standalone
                  draggable={draggable}
                  dragKind="unassigned-player"
                  pin={{
                    id: String(player.membership_id),
                    membershipId: player.membership_id,
                    label: shortLabel(player.name),
                    number: player.jersey_number,
                    photoUrl: player.photo,
                    fullName: player.name,
                    x: 50,
                    y: 50,
                  }}
                  onTap={() => onTapPlayer(player.membership_id, player.name)}
                />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
