import { getMatch } from "../../api/sport";
import { getMatchEquipment, listMovements } from "../../api/logistics";

export interface OutstandingEquipmentRow {
  matchId: number;
  opponent: string;
  eventDate: string;
  articleId: number;
  articleName: string;
  outQuantity: number;
  returnedQuantity: number;
  status: "out" | "partially_returned";
}

/**
 * Carte « Sortis pour un match » (fiche `logistique.md` §3.2) : aucun point
 * d'accès n'agrège directement « les sorties de matériel non soldées, tous
 * matchs confondus » côté `apps.logistics` (seul `matches/<id>/equipment/`
 * existe, par match). Reconstitué ici à partir du registre des mouvements
 * (matchs distincts ayant une sortie « Prêt pour un match »), puis du détail
 * par match — limitation documentée au compte rendu plutôt qu'un point
 * d'accès inventé.
 */
export async function listOutstandingMatchEquipment(): Promise<OutstandingEquipmentRow[]> {
  const movements = await listMovements({ movement_type: "out_loan", limit: 200 });
  const matchIds = [...new Set(movements.results.map((m) => m.match_id).filter((id): id is number => id != null))];
  const capped = matchIds.slice(0, 15);

  const perMatch = await Promise.all(
    capped.map(async (matchId) => {
      const [match, equipment] = await Promise.all([getMatch(matchId), getMatchEquipment(matchId)]);
      return { match, equipment };
    }),
  );

  const rows: OutstandingEquipmentRow[] = [];
  for (const { match, equipment } of perMatch) {
    for (const line of equipment.lines) {
      if (line.status === "returned") continue;
      rows.push({
        matchId: match.id,
        opponent: match.opponent,
        eventDate: match.event_date,
        articleId: line.article_id,
        articleName: line.article_name ?? "",
        outQuantity: line.out_quantity,
        returnedQuantity: line.returned_quantity,
        status: line.status,
      });
    }
  }
  rows.sort((a, b) => (a.eventDate < b.eventDate ? 1 : -1));
  return rows;
}
