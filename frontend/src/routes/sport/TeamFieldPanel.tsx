import { useState } from "react";
import type { ClubPlayerPosition } from "../../api/clubs";
import type { Formation, TeamAssignmentItem } from "../../api/sport";
import {
  FORMATION_LABELS,
  PitchBoard,
  PitchPin,
  slotsForFormation,
  usePitchDropZone,
  type FormationSlot,
  type PitchDragItem,
  type PitchPinData,
} from "../../design-system";
import { useTeamsPitchWidthStyle } from "./pitchSizing";
import { shortLabel } from "./pinLayout";

/** Filtres rapides par poste pour le banc (référence visuelle externe du
 * client du 30/09/2026, point 2 du message de recadrage de cette tâche) :
 * mêmes codes que `ClubPlayerPosition` (`api/clubs.ts`), jamais inventés. */
const BENCH_POSITION_FILTERS: Array<{ value: ClubPlayerPosition; label: string }> = [
  { value: "goalkeeper", label: "GB" },
  { value: "defender", label: "DEF" },
  { value: "midfielder", label: "MIL" },
  { value: "forward", label: "ATT" },
];

export interface ArmedPlayer {
  team: "A" | "B";
  membershipId: number;
  name: string;
}

export const MAX_ON_FIELD = 11;

/** Formations proposées pour une équipe de séance (extension client du
 * 30/09/2026, hors CDC écrit à ce jour -- voir le compte rendu). Mêmes
 * valeurs que la bibliothèque du plan tactique (`apps.sport.models.
 * Formation`), y compris « Personnalisée » : une équipe de séance compte
 * toujours jusqu'à 11 joueurs, mais rien n'oblige le Coach à suivre une
 * disposition nommée. */
export const TEAM_FORMATION_OPTIONS = Object.keys(FORMATION_LABELS) as Formation[];

function round2(value: number): number {
  return Math.round(Math.min(100, Math.max(0, value)) * 100) / 100;
}

/** Emplacements en pointillés pour une formation de séance. `null`
 * (formation pas encore choisie) ou « Personnalisée » : aucun repère
 * fixe, placement libre à l'endroit déposé (même choix que le tableau
 * noir pour les effectifs réduits, `design-system/tactics/formations.ts`). */
function slotsForTeam(formation: Formation | ""): FormationSlot[] {
  if (!formation || formation === "custom") return [];
  return slotsForFormation(formation, 11);
}

function occupantNear(assignments: TeamAssignmentItem[], x: number, y: number): TeamAssignmentItem | null {
  return (
    assignments.find(
      (a) =>
        a.is_on_field &&
        a.x_coord != null &&
        a.y_coord != null &&
        Math.abs(Number(a.x_coord) - x) < 4 &&
        Math.abs(Number(a.y_coord) - y) < 4,
    ) ?? null
  );
}

function nearestFreeSlot(slots: FormationSlot[], occupiedIds: Set<string>, x: number, y: number): FormationSlot | null {
  let best: FormationSlot | null = null;
  let bestDist = Infinity;
  for (const slot of slots) {
    if (occupiedIds.has(slot.id)) continue;
    const dist = Math.hypot(slot.x - x, slot.y - y);
    if (dist < 8 && dist < bestDist) {
      best = slot;
      bestDist = dist;
    }
  }
  return best;
}

function otherTeamOf(team: "A" | "B"): "A" | "B" {
  return team === "A" ? "B" : "A";
}

/** Un terrain + banc pour une équipe (A ou B) : extension client du
 * 30/09/2026 (plafond de 11 sur le terrain, banc pour le surplus,
 * formation au choix, glisser-déposer avec échange — voir le compte
 * rendu de cette tâche). Partagé entre la page Séance (§3.2, édition
 * complète) et le mode éditable du Vestiaire du jour (`allowCrossTeam
 * BenchDrop`, nouveau : glisser un joueur du banc d'une équipe vers le
 * banc de l'autre bascule son équipe — extension client du 30/09/2026,
 * hors CDC écrit à ce jour pour le Vestiaire). Même mécanique de glisser/
 * toucher que le tableau noir (`TableauNoirPage.tsx`), adaptée à une
 * séance : pas de plan de match, juste une répartition terrain/banc. */
export function TeamFieldPanel({
  team,
  color,
  formation,
  assignments,
  canAssign,
  allowCrossTeamBenchDrop = false,
  armed,
  onArm,
  onSetFormation,
  onPlacePlayer,
  onAssignTeam,
  onOpenFieldMenu,
  onOpenBenchMenu,
}: {
  team: "A" | "B";
  color: string;
  formation: Formation | "";
  assignments: TeamAssignmentItem[];
  canAssign: boolean;
  /** Un dépôt sur le banc de cette équipe, venant du banc (ou du terrain)
   * de l'AUTRE équipe, bascule le joueur dans cette équipe (`assignTeam`)
   * au lieu d'être ignoré. Par défaut `false` : comportement historique de
   * la page Séance, non demandé par le client pour cet écran. */
  allowCrossTeamBenchDrop?: boolean;
  armed: ArmedPlayer | null;
  onArm: (armed: ArmedPlayer | null) => void;
  onSetFormation: (team: "A" | "B", formation: Formation) => void;
  onPlacePlayer: (team: "A" | "B", membershipId: number, x: number | null, y: number | null) => void;
  onAssignTeam: (membershipId: number, team: "A" | "B") => void;
  onOpenFieldMenu: (team: "A" | "B", membershipId: number, name: string) => void;
  onOpenBenchMenu: (team: "A" | "B", membershipId: number, name: string) => void;
}) {
  const pitchWidthStyle = useTeamsPitchWidthStyle();
  const onField = assignments.filter((a) => a.is_on_field);
  const bench = assignments.filter((a) => !a.is_on_field);
  const slots = slotsForTeam(formation);

  // Recherche + filtres rapides par poste sur le banc (référence externe du
  // client du 30/09/2026, point 2 du message de recadrage de cette tâche) :
  // utiles avec un effectif nombreux. Filtre purement local à l'affichage,
  // sans effet sur les données ni sur la zone de dépose (le banc entier
  // reste la cible du glisser-déposer, filtré ou non).
  const [benchQuery, setBenchQuery] = useState("");
  const [benchPositionFilter, setBenchPositionFilter] = useState<ClubPlayerPosition | "">("");
  const filteredBench = bench.filter((item) => {
    if (benchPositionFilter && item.player.position !== benchPositionFilter) return false;
    if (benchQuery.trim()) {
      const q = benchQuery.trim().toLowerCase();
      const name = item.player.name.toLowerCase();
      const number = String(item.player.jersey_number ?? "");
      if (!name.includes(q) && !number.includes(q)) return false;
    }
    return true;
  });

  const occupiedSlotIds = new Set(
    slots
      .filter((slot) => onField.some((a) => Math.abs(Number(a.x_coord) - slot.x) < 3 && Math.abs(Number(a.y_coord) - slot.y) < 3))
      .map((slot) => slot.id),
  );

  const pins: PitchPinData[] = onField.map((item) => ({
    id: String(item.id),
    membershipId: item.membership_id,
    label: shortLabel(item.player.name),
    number: item.player.jersey_number,
    jerseyColor: color,
    photoUrl: item.player.photo,
    fullName: item.player.name,
    x: Number(item.x_coord),
    y: Number(item.y_coord),
  }));

  const boardSlots = slots.map((s) => ({ id: s.id, x: s.x, y: s.y, abbrev: s.abbrev, occupied: occupiedSlotIds.has(s.id) }));

  function placeAt(membershipId: number, x: number, y: number): void {
    const occupant = occupantNear(assignments, x, y);
    if (occupant && occupant.membership_id === membershipId) return; // déposé sur soi-même : rien à faire
    if (occupant) {
      onPlacePlayer(team, membershipId, Number(occupant.x_coord), Number(occupant.y_coord));
      return;
    }
    // Pas de case libre repérée (formation personnalisée, ou plafond de 11
    // déjà atteint) : on envoie les coordonnées brutes et on laisse le
    // service refuser explicitement un dépassement plutôt que de deviner
    // une règle de refus ici (CLAUDE.md §2 points 5/15).
    const slot = nearestFreeSlot(slots, occupiedSlotIds, x, y);
    const target = slot ?? { x: round2(x), y: round2(y) };
    onPlacePlayer(team, membershipId, round2(target.x), round2(target.y));
  }

  function handleDropOnPitch(item: PitchDragItem<{ membershipId: number }>, x: number, y: number): void {
    if (!canAssign) return;
    if (item.kind === "unassigned-player") {
      onAssignTeam(item.data.membershipId, team);
      return;
    }
    if (item.kind !== `team-${team}-member`) {
      // Pion d'une autre équipe déposé ici : bascule d'équipe (même appel
      // que le menu « Passer en … »), pas un placement sur ce terrain.
      onAssignTeam(item.data.membershipId, team);
      return;
    }
    placeAt(item.data.membershipId, x, y);
  }

  const benchDropRef = usePitchDropZone(canAssign ? `team-${team}-bench` : null, (item) => {
    if (item.kind === `team-${team}-member`) {
      onPlacePlayer(team, (item.data as { membershipId: number }).membershipId, null, null);
      return;
    }
    if (allowCrossTeamBenchDrop && item.kind === `team-${otherTeamOf(team)}-member`) {
      // Nouveau (extension client du 30/09/2026) : glisser un joueur du
      // banc (ou du terrain) de l'autre équipe sur ce banc le fait passer
      // dans cette équipe. Il atterrit sur le banc de sa nouvelle équipe,
      // pas automatiquement sur le terrain (même règle que le bouton
      // « Passer en … »).
      onAssignTeam((item.data as { membershipId: number }).membershipId, team);
    }
  });

  function handleTapPin(pin: PitchPinData): void {
    if (armed && armed.team === team) {
      placeAt(armed.membershipId, pin.x, pin.y);
      onArm(null);
      return;
    }
    onOpenFieldMenu(team, pin.membershipId, pin.label);
  }

  function handleTapSlot(slot: { id: string; x: number; y: number }): void {
    if (!armed || armed.team !== team) return;
    placeAt(armed.membershipId, slot.x, slot.y);
    onArm(null);
  }

  return (
    <div className="min-w-0 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-1 text-sm font-medium text-text">
          <span aria-hidden className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
          Équipe {team} · {onField.length}/{MAX_ON_FIELD} sur le terrain · {bench.length} sur le banc
        </p>
      </div>
      {/* Repères visuels (référence externe du client du 30/09/2026, point
       * 1 du message de recadrage de cette tâche) : l'état se lit d'un
       * coup d'œil, juste au-dessus du sélecteur de formation. */}
      <div className="flex flex-wrap items-center gap-1.5 text-xs font-medium text-text">
        <span className="inline-flex h-6 items-center rounded-full bg-surface-muted px-2">
          Système : {formation ? FORMATION_LABELS[formation] : "non choisi"}
        </span>
        <span className="inline-flex h-6 items-center rounded-full bg-surface-muted px-2">
          {onField.length}/{MAX_ON_FIELD} postes pourvus
        </span>
      </div>
      <label className="block text-xs font-medium text-text-muted">
        Formation
        <select
          className="mt-1 h-control-md w-full rounded-sm border border-border-strong bg-surface px-3 text-sm text-text disabled:opacity-60"
          value={formation}
          disabled={!canAssign}
          onChange={(e) => onSetFormation(team, e.target.value as Formation)}
        >
          <option value="" disabled>
            Choisir une formation
          </option>
          {TEAM_FORMATION_OPTIONS.map((f) => (
            <option key={f} value={f}>
              {FORMATION_LABELS[f]}
            </option>
          ))}
        </select>
      </label>
      <div style={pitchWidthStyle}>
        <PitchBoard
          mode="tactic"
          ariaLabel={`Équipe ${team}`}
          pins={pins}
          slots={boardSlots}
          dropZoneKey={canAssign ? `team-${team}-pitch` : undefined}
          onDropPlayer={handleDropOnPitch}
          onTapPin={handleTapPin}
          onTapSlot={handleTapSlot}
          pinsDraggable={canAssign}
          dragKind={`team-${team}-member`}
        />
      </div>
      <div ref={benchDropRef} data-pitch-dropzone={canAssign ? `team-${team}-bench` : undefined} className="rounded-md border border-dashed border-border-strong p-2">
        <p className="mb-1 text-xs font-medium text-text-muted">Banc</p>
        {bench.length === 0 ? (
          <p className="text-xs text-text-muted">Aucun joueur sur le banc.</p>
        ) : (
          <>
            {bench.length > 1 ? (
              <div className="mb-2 space-y-1">
                <input
                  type="text"
                  aria-label={`Rechercher sur le banc de l'équipe ${team}`}
                  placeholder="Nom ou numéro"
                  value={benchQuery}
                  onChange={(e) => setBenchQuery(e.target.value)}
                  className="h-8 w-full rounded-sm border border-border-strong bg-surface px-2 text-xs text-text placeholder:text-text-muted"
                />
                <div className="flex flex-wrap gap-1">
                  {BENCH_POSITION_FILTERS.map((f) => (
                    <button
                      key={f.value}
                      type="button"
                      onClick={() => setBenchPositionFilter((v) => (v === f.value ? "" : f.value))}
                      aria-pressed={benchPositionFilter === f.value}
                      className={[
                        "h-6 rounded-full border px-2 text-[11px] font-medium",
                        benchPositionFilter === f.value
                          ? "border-primary bg-primary text-on-primary"
                          : "border-border-strong bg-surface text-text",
                      ].join(" ")}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {filteredBench.length === 0 ? (
              <p className="text-xs text-text-muted">Aucun joueur du banc ne correspond au filtre.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {filteredBench.map((item) => (
                  <PitchPin
                    key={item.id}
                    vertical
                    standalone
                    draggable={canAssign}
                    dragKind={`team-${team}-member`}
                    pin={{
                      id: String(item.id),
                      membershipId: item.membership_id,
                      label: shortLabel(item.player.name),
                      number: item.player.jersey_number,
                      jerseyColor: color,
                      photoUrl: item.player.photo,
                      fullName: item.player.name,
                      x: 50,
                      y: 50,
                      highlighted: armed?.team === team && armed.membershipId === item.membership_id,
                    }}
                    onTap={() => onOpenBenchMenu(team, item.membership_id, shortLabel(item.player.name))}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
