import type { Formation, SquadSize } from "../../api/sport";

/**
 * Géométrie des formations, **entièrement côté client** (docs/ecrans/
 * sport-plan-tactique.md : aucune géométrie de formation n'existe côté
 * API — `TacticalPlanPlacement` ne stocke que des coordonnées libres
 * 0-100, `schema-donnees.md` §5.11). Décision de la tâche 3.7, signalée au
 * compte rendu : cette table statique fait le lien entre une formation
 * choisie (`4-4-2`…) et les emplacements en pointillés affichés sur le
 * terrain (§5.1), et sert aussi à replacer automatiquement les joueurs
 * déjà placés quand la formation change (§4.3).
 *
 * Repère : y = 0 côté propre but, y = 100 côté but adverse (« on attaque
 * vers le haut » en portrait, §7.1).
 */

export type SlotPositionKind = "goalkeeper" | "defender" | "midfielder" | "forward";

export interface FormationSlot {
  id: string;
  x: number;
  y: number;
  abbrev: string;
  positionKind: SlotPositionKind;
}

function lineLabels(prefix: string, count: number): string[] {
  if (count <= 1) return [`${prefix}C`];
  if (count === 2) return [`${prefix}G`, `${prefix}D`];
  if (count === 3) return [`${prefix}G`, `${prefix}C`, `${prefix}D`];
  if (count === 4) return [`${prefix}G`, `${prefix}C`, `${prefix}C`, `${prefix}D`];
  return [`${prefix}G`, `${prefix}C`, `${prefix}C`, `${prefix}C`, `${prefix}D`];
}

function xsFor(count: number, positionKind: SlotPositionKind): number[] {
  if (count <= 1) return [50];
  // Les attaquants se resserrent vers l'axe (ils convergent vers le but
  // adverse) : une marge plus large que les défenseurs/milieux, qui eux
  // couvrent la largeur du terrain. Sans cette distinction, une ligne de
  // 2 attaquants s'étalait jusqu'aux touches comme des ailiers (constat
  // du client, comparaison avec une référence externe).
  //
  // Un milieu à 2 est toujours une double sentinelle (seule combinaison du
  // 4-2-3-1 dans la bibliothèque, §4.11) : des joueurs tenus plus au centre
  // que les côtés, pas des ailiers. Sans cette distinction, la même marge
  // que les lignes à 4/5 plaçait la double sentinelle exactement sous les
  // deux milieux offensifs de la ligne suivante (x identiques), alignés à
  // la verticale « comme des pistons » (constat du client, capture à
  // l'appui) au lieu d'être décalés en profondeur.
  const margin = positionKind === "forward" ? 32 : count === 2 && positionKind === "midfielder" ? 28 : 12;
  const span = 100 - margin * 2;
  return Array.from({ length: count }, (_, i) => margin + (span * i) / (count - 1));
}

interface LineSpec {
  count: number;
  y: number;
  positionKind: SlotPositionKind;
  labelPrefix: string;
}

function buildSlots(lines: LineSpec[]): FormationSlot[] {
  const slots: FormationSlot[] = [];
  lines.forEach((line, lineIndex) => {
    const labels = lineLabels(line.labelPrefix, line.count);
    const xs = xsFor(line.count, line.positionKind);
    xs.forEach((x, i) => {
      slots.push({
        id: `line${lineIndex}-${i}`,
        x,
        y: line.y,
        abbrev: labels[i] ?? line.labelPrefix,
        positionKind: line.positionKind,
      });
    });
  });
  return slots;
}

const GK: LineSpec = { count: 1, y: 6, positionKind: "goalkeeper", labelPrefix: "G" };

/** Formations à 11 (CDC 4.11) — les 8 seules acceptées par l'API pour un
 * effectif de 11 (`TacticalPlan.clean`, backend/apps/sport/models.py). */
const ELEVEN_A_SIDE: Record<Exclude<Formation, "custom">, LineSpec[]> = {
  "4-4-2": [GK, { count: 4, y: 25, positionKind: "defender", labelPrefix: "D" }, { count: 4, y: 55, positionKind: "midfielder", labelPrefix: "M" }, { count: 2, y: 85, positionKind: "forward", labelPrefix: "A" }],
  "4-3-3": [GK, { count: 4, y: 24, positionKind: "defender", labelPrefix: "D" }, { count: 3, y: 50, positionKind: "midfielder", labelPrefix: "M" }, { count: 3, y: 82, positionKind: "forward", labelPrefix: "A" }],
  "4-2-3-1": [GK, { count: 4, y: 20, positionKind: "defender", labelPrefix: "D" }, { count: 2, y: 40, positionKind: "midfielder", labelPrefix: "M" }, { count: 3, y: 62, positionKind: "midfielder", labelPrefix: "M" }, { count: 1, y: 86, positionKind: "forward", labelPrefix: "A" }],
  "3-5-2": [GK, { count: 3, y: 24, positionKind: "defender", labelPrefix: "D" }, { count: 5, y: 55, positionKind: "midfielder", labelPrefix: "M" }, { count: 2, y: 85, positionKind: "forward", labelPrefix: "A" }],
  "3-4-3": [GK, { count: 3, y: 22, positionKind: "defender", labelPrefix: "D" }, { count: 4, y: 50, positionKind: "midfielder", labelPrefix: "M" }, { count: 3, y: 82, positionKind: "forward", labelPrefix: "A" }],
  "5-3-2": [GK, { count: 5, y: 22, positionKind: "defender", labelPrefix: "D" }, { count: 3, y: 55, positionKind: "midfielder", labelPrefix: "M" }, { count: 2, y: 85, positionKind: "forward", labelPrefix: "A" }],
  "4-1-4-1": [GK, { count: 4, y: 18, positionKind: "defender", labelPrefix: "D" }, { count: 1, y: 36, positionKind: "midfielder", labelPrefix: "M" }, { count: 4, y: 60, positionKind: "midfielder", labelPrefix: "M" }, { count: 1, y: 86, positionKind: "forward", labelPrefix: "A" }],
  "4-5-1": [GK, { count: 4, y: 22, positionKind: "defender", labelPrefix: "D" }, { count: 5, y: 55, positionKind: "midfielder", labelPrefix: "M" }, { count: 1, y: 86, positionKind: "forward", labelPrefix: "A" }],
};

/** Effectifs réduits (7, 8) : seule la formation « Personnalisée » est
 * acceptée par l'API pour ces effectifs (contrainte de modèle backend,
 * `TacticalPlan.clean` — point ouvert du CDC non tranché, sport-plan-
 * tactique.md §8 point 3). Cette disposition ne sert donc que de point de
 * départ visuel modifiable librement ; le formulaire « Nouveau plan »
 * n'y propose jamais que « Personnalisée » (voir compte rendu). */
const REDUCED_DEFAULT: Record<7 | 8, LineSpec[]> = {
  7: [GK, { count: 2, y: 28, positionKind: "defender", labelPrefix: "D" }, { count: 3, y: 58, positionKind: "midfielder", labelPrefix: "M" }, { count: 1, y: 86, positionKind: "forward", labelPrefix: "A" }],
  8: [GK, { count: 3, y: 26, positionKind: "defender", labelPrefix: "D" }, { count: 3, y: 56, positionKind: "midfielder", labelPrefix: "M" }, { count: 1, y: 86, positionKind: "forward", labelPrefix: "A" }],
};

/** Formations utilisables selon l'effectif — n'expose jamais une
 * combinaison que le service refuserait (point ouvert signalé dans la
 * tâche : `POST /tactical-plans/` renvoie une 500 non traduite sur une
 * combinaison invalide, faute de validation côté vue de création). */
export function formationsForSquadSize(squadSize: SquadSize): Formation[] {
  if (squadSize === 11) return [...(Object.keys(ELEVEN_A_SIDE) as Formation[])];
  return ["custom"];
}

export function slotsForFormation(formation: Formation, squadSize: SquadSize): FormationSlot[] {
  if (squadSize !== 11 || formation === "custom") {
    return buildSlots(REDUCED_DEFAULT[squadSize === 11 ? 8 : squadSize]);
  }
  const lines = ELEVEN_A_SIDE[formation];
  return buildSlots(lines ?? ELEVEN_A_SIDE["4-4-2"]);
}

export const FORMATION_LABELS: Record<Formation, string> = {
  "4-4-2": "4-4-2",
  "4-3-3": "4-3-3",
  "4-2-3-1": "4-2-3-1",
  "3-5-2": "3-5-2",
  "3-4-3": "3-4-3",
  "5-3-2": "5-3-2",
  "4-1-4-1": "4-1-4-1",
  "4-5-1": "4-5-1",
  custom: "Personnalisée",
};
