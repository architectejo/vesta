import type { TeamAssignmentItem } from "../../api/sport";
import type { PitchPinData } from "../../design-system";

/** Pions réellement placés sur le terrain (`is_on_field`), aux vraies
 * coordonnées renvoyées par l'API (`serialize_team_assignment`). Partagé
 * entre `VestiairePage` (vue « Équipes A/B ») et `VestiaireDuJourCard`
 * (carte compacte de l'accueil, Président) : aucun joueur sur le banc
 * (`is_on_field: false`) n'a de coordonnées exploitables, il est donc
 * laissé de côté ici et listé séparément par l'écran appelant. */
export function pitchPinsForTeam(items: TeamAssignmentItem[], color: string): PitchPinData[] {
  return items
    .filter((item) => item.is_on_field && item.x_coord != null && item.y_coord != null)
    .map((item) => ({
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
}

export function shortLabel(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length < 2) return fullName;
  const first = parts[0];
  const last = parts[parts.length - 1];
  return `${first} ${last?.[0] ?? ""}.`;
}
