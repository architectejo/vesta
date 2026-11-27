import type { ClubPlayerPosition } from "../../api/clubs";

/**
 * Regroupement des joueurs par poste habituel (docs/ecrans/sport-feuille-de-
 * match.md §4.1 : puces « Tous », « Gardiens », « Défenseurs », « Milieux »,
 * « Attaquants » ; tri par poste puis nom). Demande du client (remarques.md) :
 * le Coach voit la liste subdivisée par poste pour répartir les joueurs.
 *
 * Purement d'affichage : le poste est le code renvoyé par l'API
 * (`ClubPlayerPosition`), jamais déduit ici. Le champ est facultatif côté
 * API (import historique) : un poste vide ou inconnu forme le groupe
 * « Sans poste », visible seulement sous « Tous » (aucune puce dédiée, la
 * spec n'en prévoit pas).
 */
export const POSITION_FILTER_OPTIONS: Array<{ value: ClubPlayerPosition; label: string }> = [
  { value: "goalkeeper", label: "Gardiens" },
  { value: "defender", label: "Défenseurs" },
  { value: "midfielder", label: "Milieux" },
  { value: "forward", label: "Attaquants" },
];

export const ALL_POSITIONS_LABEL = "Tous";
export const NO_POSITION_LABEL = "Sans poste";

export type PositionFilter = ClubPlayerPosition | "";
export type PositionGroupKey = ClubPlayerPosition | "none";

const ORDER: readonly PositionGroupKey[] = ["goalkeeper", "defender", "midfielder", "forward", "none"];

/** Clé de groupe d'un code de poste brut ; vide ou inconnu : « none ». */
export function positionGroupKey(position: string | null | undefined): PositionGroupKey {
  const known = POSITION_FILTER_OPTIONS.find((o) => o.value === position);
  return known ? known.value : "none";
}

export function positionGroupLabel(key: PositionGroupKey): string {
  if (key === "none") return NO_POSITION_LABEL;
  return POSITION_FILTER_OPTIONS.find((o) => o.value === key)!.label;
}

/** « Tous » laisse tout passer ; une puce ne garde que son poste (jamais « Sans poste »). */
export function matchesPositionFilter(position: string | null | undefined, filter: PositionFilter): boolean {
  return filter === "" || position === filter;
}

/** Tri stable : gardiens, défenseurs, milieux, attaquants, sans poste ; puis nom affiché. */
export function compareByPositionThenName(
  a: { position: string | null | undefined; name: string },
  b: { position: string | null | undefined; name: string },
): number {
  const rank = ORDER.indexOf(positionGroupKey(a.position)) - ORDER.indexOf(positionGroupKey(b.position));
  if (rank !== 0) return rank;
  return a.name.localeCompare(b.name, "fr", { sensitivity: "base" });
}

export interface PositionGroup<T> {
  key: PositionGroupKey;
  label: string;
  items: T[];
}

/** Groupes non vides, dans l'ordre des postes ; l'ordre interne d'origine est conservé. */
export function groupByPosition<T>(items: T[], getPosition: (item: T) => string | null | undefined): PositionGroup<T>[] {
  return ORDER.map((key) => ({
    key,
    label: positionGroupLabel(key),
    items: items.filter((item) => positionGroupKey(getPosition(item)) === key),
  })).filter((group) => group.items.length > 0);
}
